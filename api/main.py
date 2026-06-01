import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from api.routes import animes, genres, episodes, download
from api.deps import init_db, close_db

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
    description="API de dados de animes com scraper automatico e integracao CDN IPTV",
    version="2.0.0",
    lifespan=lifespan,
)

app.include_router(animes.router)
app.include_router(genres.router)
app.include_router(episodes.router)
app.include_router(download.router)


@app.get("/")
async def root():
    return {
        "name": "anm-db API",
        "version": "2.0.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
