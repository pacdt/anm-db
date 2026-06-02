"""
Mapa estatico de generos e temas Jikan (EN) -> PT-BR.

O Jikan retorna generos em ingles. Para a API ficar em PT-BR para o
publico brasileiro, mantemos um dicionario canonico.

Quando um genero nao estiver no mapa, retorna o nome original.
"""

from __future__ import annotations


# 21 generos canonicos do Jikan (https://myanimelist.net/anime/genre)
GENRE_PT_MAP: dict[str, str] = {
    "Action": "Ação",
    "Adventure": "Aventura",
    "Avant Garde": "Vanguarda",
    "Award Winning": "Premiados",
    "Boys Love": "Boys Love",
    "Comedy": "Comédia",
    "Drama": "Drama",
    "Ecchi": "Ecchi",
    "Erotica": "Erótico",
    "Fantasy": "Fantasia",
    "Girls Love": "Girls Love",
    "Gourmet": "Gastronomia",
    "Hentai": "Hentai",
    "Horror": "Terror",
    "Mystery": "Mistério",
    "Romance": "Romance",
    "Sci-Fi": "Ficção Científica",
    "Slice of Life": "Slice of Life",
    "Sports": "Esportes",
    "Supernatural": "Sobrenatural",
    "Suspense": "Suspense",
}

# Demographics (5)
DEMOGRAPHIC_PT_MAP: dict[str, str] = {
    "Kids": "Infantil",
    "Josei": "Josei",
    "Seinen": "Seinen",
    "Shounen": "Shounen",
    "Shoujo": "Shoujo",
}

# Themes (41+)
THEME_PT_MAP: dict[str, str] = {
    "Psychological": "Psicológico",
    "Gag Humor": "Humor",
    "Harem": "Harém",
    "Mecha": "Mecha",
    "Music": "Musical",
    "Parody": "Paródia",
    "Samurai": "Samurai",
    "School": "Escolar",
    "Space": "Espacial",
    "Strategy Game": "Jogo de Estratégia",
    "Super Power": "Superpoderes",
    "Vampire": "Vampiro",
    "Combat Sports": "Esportes de Combate",
    "Visual Arts": "Artes Visuais",
    "Detective": "Detetive",
    "Historical": "Histórico",
    "Idols (Female)": "Idols (Feminino)",
    "Idols (Male)": "Idols (Masculino)",
    "Love Polygon": "Triângulo Amoroso",
    "Mahou Shoujo": "Garota Mágica",
    "Military": "Militar",
    "Mythology": "Mitologia",
    "Racing": "Corrida",
    "Team Sports": "Esportes Coletivos",
    "Time Travel": "Viagem no Tempo",
    "Workplace": "Ambiente de Trabalho",
    "CGDCT": "Cotidiano Fofo",
    "Delinquents": "Delinquentes",
    "Childcare": "Cuidados Infantis",
    "Educational": "Educacional",
    "Anthropomorphic": "Antropomórfico",
    "Iyashikei": "Cura Emocional",
    "Otaku Culture": "Cultura Otaku",
    "Reverse Harem": "Harém Reverso",
    "Showbiz": "Showbiz",
    "Survival": "Sobrevivência",
    "Medical": "Médico",
    "Memoir": "Memórias",
    "Organized Crime": "Crime Organizado",
    "Performing Arts": "Artes Performáticas",
    "Pets": "Animais de Estimação",
    "Rere Contest": "Amor de Infância",
    "Tennis": "Tênis",
    "Boxing": "Boxe",
    "Martial Arts": "Artes Marciais",
    "Judo": "Judô",
    "Kung Fu": "Kung Fu",
    "Firefighters": "Bombeiros",
    "Swimming": "Natação",
    "Volleyball": "Vôlei",
    "Basketball": "Basquete",
    "Baseball": "Baseball",
    "Football": "Futebol",
    "Cycling": "Ciclismo",
    "Rugby": "Rugby",
    "Skiing": "Esqui",
    "Table Tennis": "Tênis de Mesa",
    "Wrestling": "Luta Livre",
    "Crossdressing": "Cross-dressing",
    "Gender Bender": "Troca de Gênero",
    "Gore": "Gore",
    "Loli": "Loli",
    "Shota": "Shota",
    "Yuri": "Yuri",
    "Yaoi": "Yaoi",
    "Cars": "Carros",
    "Treasure Hunt": "Caça ao Tesouro",
}


def translate_genre(nome: str) -> str:
    """Retorna a traducao PT-BR ou o nome original se nao houver mapeamento."""
    if not nome:
        return nome
    return (
        GENRE_PT_MAP.get(nome)
        or DEMOGRAPHIC_PT_MAP.get(nome)
        or THEME_PT_MAP.get(nome)
        or nome
    )


def all_known() -> set[str]:
    """Retorna todos os generos/temas conhecidos (para validacao)."""
    return set(GENRE_PT_MAP) | set(DEMOGRAPHIC_PT_MAP) | set(THEME_PT_MAP)
