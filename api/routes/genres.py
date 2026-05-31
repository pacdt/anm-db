from fastapi import APIRouter, Depends, Query, HTTPException
from api.schemas import AnimeSummary, GenreOut, PaginatedResponse
from api.deps import get_db
from db import DatabaseManager

router = APIRouter(prefix="/genres", tags=["genres"])


@router.get("")
async def list_genres(db: DatabaseManager = Depends(get_db)):
    genres = await db.list_generos()
    return [GenreOut(id=g["id"], nome=g["nome"], count=g["count"]).model_dump() for g in genres]


@router.get("/{nome}", response_model=PaginatedResponse)
async def get_genre(
    nome: str,
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=1, le=100),
    db: DatabaseManager = Depends(get_db),
):
    animes, total = await db.get_animes_by_genero(nome, page, limit)
    if total == 0:
        raise HTTPException(status_code=404, detail="Genre not found")

    pages = (total + limit - 1) // limit

    items = [
        AnimeSummary(
            title=a.get("titulo_en") or a.get("titulo"),
            slug=a["slug"],
            image=a.get("imagem"),
            score=a.get("score"),
            type=a.get("tipo"),
        ).model_dump()
        for a in animes
    ]

    return PaginatedResponse(
        items=items, total=total, page=page, limit=limit, pages=pages
    )
