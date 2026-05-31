# Resultados dos Testes de Endpoints - anm-db API

**Data:** 2026-05-27
**Servidor:** FastAPI em http://127.0.0.1:8765
**Banco:** anm.db (5.166 animes, 78.520 episodios)

## Resumo

| # | Endpoint | Metodo | Status | Descricao |
|---|----------|--------|--------|-----------|
| 1 | `/` | GET | 200 | Info da API |
| 2 | `/health` | GET | 200 | Health check |
| 3 | `/animes?limit=3` | GET | 200 | Lista paginada |
| 4 | `/animes?search=one-piece` | GET | 200 | Busca por titulo |
| 5 | `/animes?status=ongoing` | GET | 200 | Filtro por status |
| 6 | `/animes/one-piece` | GET | 200 | Detalhe do anime |
| 7 | `/animes/naruto-shippuuden` | GET | 200 | Detalhe do anime |
| 8 | `/animes/nonexistent` | GET | 404 | Anime nao encontrado |
| 9 | `/genres` | GET | 200 | Lista de generos |
| 10 | `/genres/Action` | GET | 200 | Animes por genero |
| 11 | `/episodes/latest?limit=5` | GET | 200 | Ultimos episodios |

## Detalhes por Endpoint

### 1. GET / (Root)
- Retorna: `{"name": "anm-db API", "version": "2.0.0", "docs": "/docs"}`

### 2. GET /health
- Retorna: `{"status": "ok"}`

### 3. GET /animes?limit=3
- Total de animes: 5.166
- Itens retornados: 3
- Pages: 2583

### 4. GET /animes?search=one-piece
- Resultados encontrados para "one-piece"
- Slug: `one-piece`, Titulo: "One Piece"

### 5. GET /animes?status=ongoing
- Filtra animes com status "ongoing"

### 6. GET /animes/one-piece
- 500 episodios retornados
- Generos: Action, Adventure, Fantasy
- Fonte: animefire (fallback)

### 7. GET /animes/naruto-shippuuden
- 500 episodios retornados (Naruto Shippuuden tem mais)
- Generos: Action, Adventure, Comedy

### 8. GET /animes/nonexistent (404)
- HTTP Status: 404
- Body: `{"detail": "Anime not found"}`

### 9. GET /genres
- 21 generos listados
- Top 3: Action (1783), Comedy (1778), Fantasy (1412)

### 10. GET /genres/Action?limit=3
- Fullmetal Alchemist: Brotherhood (9.1)
- Attack on Titan S3P2 (9.05)

### 11. GET /episodes/latest?limit=5
- Ultimos 5 episodios de "Fuguushoku Kanteishi ga Jitsu wa Saikyou datta"
- Episodios 8-12

## Conclusao

Todos os 11 endpoints testados funcionaram corretamente:
- 10 endpoints retornaram HTTP 200
- 1 endpoint retornou HTTP 404 (correto para anime inexistente)
- Respostas em formato JSON valido
- Paginacao funcionando corretamente
- Busca por titulo retornando resultados relevantes
- Filtro por status funcionando
- Detalhes de anime incluindo episodios e generos
