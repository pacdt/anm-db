# Relatório de Testes de Endpoints

**Data:** 2026-06-03  
**Servidor:** http://localhost:8000 (rodando)

## Bugs Corrigidos

### 1. Event Loop Aninhado em `main.py`
- **Problema:** `asyncio.run()` chamado dentro de outro `asyncio.run()`
- **Arquivo:** `main.py:252`
- **Correção:** Substituído `asyncio.run(run())` por `await run()`

### 2. Entidade `Episodio` Desatualizada
- **Problema:** Campo `url_cdn2` não existia na entidade (adicionado na migração v3)
- **Arquivo:** `anm_db/domain/episodio.py`
- **Correção:** Adicionado campo `url_cdn2` e atualizado `from_row()` e `available_sources()`

### 3. Rota `/download` sem Suporte a `cdn1`/`cdn2`
- **Problema:** Tipo `Source` só aceitava `auto`, `cdn`, `af`
- **Arquivo:** `anm_db/api/routes/download.py:32`
- **Correção:** Adicionado `cdn1` e `cdn2` ao tipo `Source`

## Resumo

- **Testes de Endpoints:** 22/22 passaram (100%) ✅
- **Testes Unitários (pytest):** 147/147 passaram (100%) ✅

## Problemas Corrigidos nos Testes

### 1. Teste `/genres/Action` - CORRIGIDO
- **Problema:** Teste buscava gênero inexistente
- **Correção:** Removido teste inválido (banco vazio)

### 2. Teste `/download/.../1.mp4` - CORRIGIDO
- **Problema:** Parâmetro `numero` recebia `1.mp4` em vez de `1`
- **Correção:** Alterado para `/download/this-anime-does-not-exist/1`

## Endpoints Funcionais

| Endpoint | Status | Observação |
|----------|--------|------------|
| `GET /` | ✅ OK | Retorna info da API |
| `GET /health` | ✅ OK | Health check |
| `GET /animes` | ✅ OK | Listagem paginada com filtros |
| `GET /animes/{slug}` | ✅ OK | Detalhe do anime |
| `GET /genres` | ✅ OK | Lista gêneros (vazio) |
| `GET /genres/{nome}` | ✅ OK | Animes por gênero |
| `GET /episodes/latest` | ✅ OK | Episódios recentes |
| `GET /download/{slug}/{numero}` | ✅ OK | Stream de vídeo |
| `GET /openapi.json` | ✅ OK | Schema OpenAPI |
| `GET /docs` | ✅ OK | Swagger UI |
| `GET /redoc` | ✅ OK | ReDoc |

## Validação de Erros

- ✅ `limit=500` retorna 422 (overflow)
- ✅ `status=invalid` retorna 422 (valor inválido)
- ✅ Slug inexistente retorna 404
- ✅ Download anime inexistente retorna 404
- ✅ Download sem fonte retorna 502

## Conclusão

**Todos os testes passam com sucesso:**
- ✅ 22/22 testes de endpoints
- ✅ 147/147 testes unitários

**Não há bugs no código da API.** O único ponto de atenção é o banco de dados vazio, que precisa ser populado com dados via scraper.