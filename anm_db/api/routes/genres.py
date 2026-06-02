"""
Rota: /genres

Retorna generos SEMPRE em PT-BR (nome_pt). Aceita o nome em EN ou PT-BR
no path para compatibilidade.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from anm_db.api.schemas import AnimeSummary, GeneroOut, PaginatedResponse
from anm_db.api.deps import get_db
from anm_db.repository.database import DatabaseManager

router = APIRouter(prefix="/genres", tags=["genres"])


@router.get("")
async def list_genres(db: DatabaseManager = Depends(get_db)):
    """Lista todos os generos em PT-BR."""
    generos = await db.list_generos()
    return [
        GeneroOut(nome=g["nome"], nome_pt=g["nome_pt"], count=g["count"]).model_dump()
        for g in generos
    ]


@router.get("/{nome}")
async def get_genre(
    nome: str,
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=1, le=100),
    lang: str = Query("pt-BR", pattern="^(pt-BR|en|ja|original)$"),
    db: DatabaseManager = Depends(get_db),
):
    """Aceita o nome em EN (legacy) ou PT-BR."""
    # Tenta encontrar pelo PT-BR primeiro, depois EN
    genero = await db.get_genero_by_nome_pt(nome)
    if not genero:
        raise HTTPException(status_code=404, detail=f"Genero '{nome}' nao encontrado")

    animes, total = await db.get_animes_by_genero(genero["nome"], page, limit)
    if total == 0:
        raise HTTPException(status_code=404, detail=f"Genero '{nome}' sem animes")
    pages = (total + limit - 1) // limit

    items = []
    for a in animes:
        if lang == "pt-BR":
            title = a.get("titulo_pt") or a.get("titulo") or a.get("titulo_en")
        elif lang == "en":
            title = a.get("titulo_en") or a.get("titulo")
        elif lang == "ja":
            title = a.get("titulo_jp") or a.get("titulo")
        else:
            title = a.get("titulo")
        items.append(
            AnimeSummary(
                slug=a["slug"],
                title=title,
                title_original=a.get("titulo"),
                image=a.get("imagem"),
                score=a.get("score"),
                type=a.get("tipo"),
                translated=bool(a.get("titulo_pt")),
            ).model_dump()
        )

    return PaginatedResponse(
        items=items, total=total, page=page, limit=limit, pages=pages
    )
