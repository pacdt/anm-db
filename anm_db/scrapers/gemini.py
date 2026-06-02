"""
Cliente Gemini (Google AI Generative Language API) para traducao PT-BR.

Rate limit: 15 RPM (free tier).
Implementa batching, retry com backoff, contador diario e deteccao de quota excedida.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any

import aiohttp

from anm_db.config import get_settings

logger = logging.getLogger("Gemini")


GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# Limite razoavel: o tier gratuito do Gemini 2.5 Flash aceita ate ~250k tokens/min.
# Em chamadas normais raramente estouramos isso, mas evitamos timeout ajustando timeout alto.
REQUEST_TIMEOUT = 60  # segundos
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2.0  # 2s, 4s, 8s


SYSTEM_PROMPT = """Voce e um tradutor profissional de animes para portugues brasileiro (PT-BR).
Recebe uma lista JSON de objetos. Para cada um, retorne a traducao no mesmo array JSON,
na MESMA ORDEM, com os campos "id" (inalterado), "titulo_pt" e "sinopse_pt".

REGRAS:
- Mantenha nomes proprios ocidentalizados (One Piece = "One Piece", NAO "Um Pedaco")
- "Adventure" -> "Aventura", "Action" -> "Acao" (ja vem traduzido em outras camadas, mas mantenha consistencia)
- Preserve referencias a termos japoneses conhecidos (sensei, senpai, onii-chan) quando apropriado
- Tom: natural, como sites especializados em anime (AnimeFire, Animes Online)
- Sinopse: traduza integralmente, mantendo o estilo descritivo
- Titulo: traduza apenas se o original NAO estiver em PT-BR (se ja for PT-BR, mantenha)
- NAO inclua comentarios, markdown, ou texto extra - APENAS o JSON array
- Se o input estiver vazio ou invalido, retorne []

ENTRADA:
{input_json}

SAIDA (APENAS o JSON, sem markdown):"""


class GeminiQuotaExceeded(Exception):
    """Quota diaria ou de tokens excedida."""


class GeminiClient:
    """Cliente assincrono para a API Gemini com rate limiting e retry."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        rpm: int | None = None,
        rpd: int | None = None,
        session: aiohttp.ClientSession | None = None,
    ):
        settings = get_settings()
        self.api_key = api_key or settings.gemini_api_key
        self.model = model or settings.gemini_model
        self.rpm = rpm or settings.gemini_rpm
        self.rpd = rpd or settings.gemini_rpd

        self.daily_counter = 0
        self._session = session
        self._owns_session = session is None
        self._lock = asyncio.Lock()
        self._last_request_ts = 0.0

    @property
    def available(self) -> bool:
        return bool(self.api_key) and self.daily_counter < self.rpd

    @property
    def _min_interval(self) -> float:
        """Intervalo minimo entre requests em segundos."""
        return 60.0 / max(self.rpm, 1)

    async def __aenter__(self) -> "GeminiClient":
        if self._session is None:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            )
        return self

    async def __aexit__(self, *exc) -> None:
        if self._owns_session and self._session:
            await self._session.close()
            self._session = None

    async def translate_batch(
        self, items: list[dict], target: str = "pt-BR"
    ) -> list[dict]:
        """Traduz um batch de animes.
        items: [{"id": int, "titulo": str, "sinopse": str}, ...]
        returns: [{"id": int, "titulo_pt": str, "sinopse_pt": str, "_usage": {...}}, ...]
        """
        if not items:
            return []
        if not self.api_key:
            logger.debug("Gemini API key nao configurada, pulando batch")
            return []
        if not self.available:
            logger.warning(
                f"Gemini quota diaria atingida ({self.daily_counter}/{self.rpd})"
            )
            raise GeminiQuotaExceeded("daily quota")

        # Filtra apenas items com conteudo para traduzir
        valid = [
            i
            for i in items
            if (i.get("sinopse") or i.get("titulo"))
        ]
        if not valid:
            return []

        async with self._lock:
            await self._wait_rate_limit()
            prompt_input = json.dumps(
                [
                    {
                        "id": i["id"],
                        "titulo": i.get("titulo") or "",
                        "sinopse": i.get("sinopse") or "",
                    }
                    for i in valid
                ],
                ensure_ascii=False,
            )
            prompt = SYSTEM_PROMPT.format(input_json=prompt_input)
            try:
                response_text, usage = await self._call_with_retry(prompt)
                self.daily_counter += 1
                parsed = self._parse_response(response_text, valid)
                if usage:
                    for item in parsed:
                        item["_usage"] = usage
                return parsed
            except GeminiQuotaExceeded:
                raise
            except Exception as e:
                logger.error(f"Erro Gemini translate_batch: {e}")
                return []

    async def _wait_rate_limit(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_request_ts
        if elapsed < self._min_interval:
            await asyncio.sleep(self._min_interval - elapsed)
        self._last_request_ts = time.monotonic()

    async def _call_with_retry(self, prompt: str) -> tuple[str, dict | None]:
        url = f"{GEMINI_BASE}/{self.model}:generateContent"
        params = {"key": self.api_key}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "topP": 0.8,
                "maxOutputTokens": 8192,
                "responseMimeType": "application/json",
            },
        }

        last_exc = None
        for attempt in range(MAX_RETRIES):
            try:
                assert self._session is not None
                async with self._session.post(
                    url, params=params, json=payload
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return self._extract_text_and_usage(data)
                    if resp.status == 429:
                        # Rate limit por minuto. Espera 60s.
                        body = await resp.text()
                        logger.warning(
                            f"Gemini 429 (RPM) tentativa {attempt + 1}/{MAX_RETRIES}: {body[:200]}"
                        )
                        if "quota" in body.lower() or "exceeded" in body.lower():
                            raise GeminiQuotaExceeded(body[:200])
                        await asyncio.sleep(60)
                        continue
                    if resp.status == 403:
                        body = await resp.text()
                        logger.error(f"Gemini 403: {body[:300]}")
                        if "quota" in body.lower():
                            raise GeminiQuotaExceeded(body[:200])
                        return "", None
                    if resp.status in (500, 502, 503, 504):
                        logger.warning(
                            f"Gemini {resp.status} tentativa {attempt + 1}/{MAX_RETRIES}"
                        )
                        await asyncio.sleep(RETRY_BACKOFF_BASE ** (attempt + 1))
                        continue
                    body = await resp.text()
                    logger.error(f"Gemini HTTP {resp.status}: {body[:300]}")
                    return "", None
            except GeminiQuotaExceeded:
                raise
            except asyncio.TimeoutError as e:
                last_exc = e
                logger.warning(
                    f"Gemini timeout tentativa {attempt + 1}/{MAX_RETRIES}"
                )
                await asyncio.sleep(RETRY_BACKOFF_BASE ** (attempt + 1))
            except Exception as e:
                last_exc = e
                logger.warning(
                    f"Gemini erro tentativa {attempt + 1}/{MAX_RETRIES}: {e}"
                )
                await asyncio.sleep(RETRY_BACKOFF_BASE ** (attempt + 1))

        if last_exc:
            raise last_exc
        return "", None

    def _extract_text_and_usage(self, data: dict) -> tuple[str, dict | None]:
        candidates = data.get("candidates") or []
        if not candidates:
            return "", None
        content = candidates[0].get("content") or {}
        parts = content.get("parts") or []
        text = "".join(p.get("text", "") for p in parts)
        usage_meta = data.get("usageMetadata") or {}
        usage = None
        if usage_meta:
            usage = {
                "input": usage_meta.get("promptTokenCount"),
                "output": usage_meta.get("candidatesTokenCount"),
            }
        return text, usage

    def _parse_response(
        self, response_text: str, original_items: list[dict]
    ) -> list[dict]:
        """Extrai o JSON array da resposta do Gemini (modelos as vezes adicionam markdown)."""
        text = response_text.strip()
        # Remove markdown fences se presentes
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        # Tenta parse direto
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return self._validate_results(data, original_items)
        except json.JSONDecodeError:
            pass
        # Tenta extrair primeiro array JSON do texto
        match = re.search(r"\[\s*\{.*\}\s*\]", text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
                if isinstance(data, list):
                    return self._validate_results(data, original_items)
            except json.JSONDecodeError:
                pass
        logger.error(
            f"Gemini resposta nao e JSON array: {text[:200]}"
        )
        return []

    def _validate_results(
        self, parsed: list[Any], original_items: list[dict]
    ) -> list[dict]:
        """Garante que cada item de saida tem id, titulo_pt, sinopse_pt."""
        out = []
        for entry in parsed:
            if not isinstance(entry, dict):
                continue
            entry_id = entry.get("id")
            if entry_id is None:
                continue
            out.append(
                {
                    "id": entry_id,
                    "titulo_pt": entry.get("titulo_pt") or None,
                    "sinopse_pt": entry.get("sinopse_pt") or None,
                }
            )
        return out
