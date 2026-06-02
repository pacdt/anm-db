"""
Servico de traducao PT-BR.

Orquestra o GeminiClient para traduzir titulo + sinopse dos animes
que ainda nao possuem traducao. Idempotente: nao sobrescreve dados
Jikan originais (titulo_pt e sinopse_pt sao campos separados).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from anm_db.config import get_settings
from anm_db.repository.database import DatabaseManager
from anm_db.scrapers.gemini import GeminiClient, GeminiQuotaExceeded

logger = logging.getLogger("Translator")


@dataclass
class TranslationReport:
    total: int = 0
    translated: int = 0
    failed: int = 0
    skipped: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "translated": self.translated,
            "failed": self.failed,
            "skipped": self.skipped,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }


class AnimeTranslator:
    def __init__(
        self,
        db: DatabaseManager,
        gemini: GeminiClient | None = None,
        batch_size: int | None = None,
    ):
        settings = get_settings()
        self.db = db
        self.gemini = gemini or GeminiClient()
        self.batch_size = batch_size or settings.translation_batch_size

    async def translate_pending(self, limit: int = 500) -> TranslationReport:
        """Traduz todos os animes com titulo_pt OU sinopse_pt ausentes.
        Idempotente: se um campo ja tem PT-BR, nao re-traduz.
        """
        report = TranslationReport()
        candidates = await self.db.list_animes_pending_translation(limit=limit)
        report.total = len(candidates)
        logger.info(f"Traducao PT-BR: {report.total} animes candidatos")

        if not candidates:
            return report

        if not self.gemini.api_key:
            logger.warning("GEMINI_API_KEY nao configurada, pulando traducao")
            report.skipped = report.total
            for anime in candidates:
                await self.db.log_translation(
                    anime_id=anime["id"],
                    provider=self.gemini.model,
                    status="skipped_no_key",
                )
            return report

        for i in range(0, len(candidates), self.batch_size):
            batch = candidates[i : i + self.batch_size]
            try:
                results = await self.gemini.translate_batch(
                    [
                        {
                            "id": a["id"],
                            "titulo": a.get("titulo_en") or a.get("titulo") or "",
                            "sinopse": a.get("sinopse") or "",
                        }
                        for a in batch
                    ]
                )
            except GeminiQuotaExceeded:
                logger.warning("Gemini quota diaria atingida, parando lote")
                report.skipped += len(batch)
                for a in batch:
                    await self.db.log_translation(
                        anime_id=a["id"],
                        provider=self.gemini.model,
                        status="skipped_quota",
                    )
                break
            except Exception as e:
                logger.error(f"Erro no batch de traducao: {e}")
                report.failed += len(batch)
                continue

            by_id = {r["id"]: r for r in results}
            for anime in batch:
                r = by_id.get(anime["id"])
                if not r:
                    report.failed += 1
                    await self.db.log_translation(
                        anime_id=anime["id"],
                        provider=self.gemini.model,
                        status="error",
                        erro_msg="resposta vazia",
                    )
                    continue
                usage = r.get("_usage") or {}
                input_tokens = usage.get("input")
                output_tokens = usage.get("output")
                await self.db.update_translation(
                    anime_id=anime["id"],
                    titulo_pt=r.get("titulo_pt"),
                    sinopse_pt=r.get("sinopse_pt"),
                    model=self.gemini.model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
                await self.db.log_translation(
                    anime_id=anime["id"],
                    provider=self.gemini.model,
                    status="success",
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
                report.translated += 1
                report.input_tokens += input_tokens or 0
                report.output_tokens += output_tokens or 0

            # Nota: report.failed ja foi incrementado dentro do loop para cada item sem resposta

            # Respiro entre batches para nao estourar RPM
            await asyncio.sleep(1.0)

        logger.info(
            f"Traducao concluida: {report.translated}/{report.total} ok, "
            f"{report.failed} falhas, {report.skipped} skipados, "
            f"{report.input_tokens + report.output_tokens} tokens"
        )
        return report
