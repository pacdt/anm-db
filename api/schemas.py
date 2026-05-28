from pydantic import BaseModel


class AnimeSummary(BaseModel):
    title: str | None = None
    slug: str
    image: str | None = None
    score: float | None = None
    type: str | None = None


class AnimeDetail(BaseModel):
    id: int
    mal_id: int | None = None
    slug: str
    tipo: str | None = None
    titulo: str | None = None
    titulo_en: str | None = None
    titulo_jp: str | None = None
    imagem: str | None = None
    score: float | None = None
    sinopse: str | None = None
    trailer_url: str | None = None
    status: str | None = None
    genres: list[str] = []
    episodes: list[dict] = []
    skip_times: dict = {}


class EpisodeOut(BaseModel):
    id: int
    anime_id: int
    numero: int
    titulo: str | None = None
    url_cdn: str | None = None
    url_af: str | None = None
    fonte_ativa: str | None = None
    slug: str | None = None
    anime_title: str | None = None
    anime_image: str | None = None
    tipo: str | None = None


class GenreOut(BaseModel):
    id: int
    nome: str
    count: int


class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    limit: int
    pages: int
