"""
FastAPI app principal.

Startup: conecta ao DB via DatabaseManager singleton.
Shutdown: fecha conexao.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from anm_db.api.deps import close_db, init_db
from anm_db.api.routes import animes, episodes, genres
from anm_db.api.routes.download import router as download_router

logger = logging.getLogger("API")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info("API iniciada com banco conectado")
    yield
    await close_db()
    logger.info("API finalizada")


app = FastAPI(
    title="anm-db API",
    description="API de dados de animes com scraper automatico, integracao CDN IPTV, "
                "sincronizacao Jikan, skip times Aniskip e traducao PT-BR via Gemini.",
    version="2.0.0",
    lifespan=lifespan,
)

app.include_router(animes.router)
app.include_router(genres.router)
app.include_router(episodes.router)
app.include_router(download_router)


@app.get("/")
async def root():
    return {
        "name": "anm-db API",
        "version": "2.0.0",
        "docs": "/docs",
        "features": {
            "languages": ["pt-BR", "en", "ja", "original"],
            "translation_provider": "gemini",
            "video_download": ["mp4", "ts", "hls"],
        },
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
