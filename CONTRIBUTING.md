# Contribuindo para anm-db

## Guia de Contribuicao

### Ambiente de Desenvolvimento

```bash
git clone https://github.com/pacdt/anm-db.git
cd anm-db
git checkout refactor/database-migration
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Como Rodar o Migrador

```bash
# Migra dados JSON existentes para SQLite
python main.py --mode=migrate

# O banco sera criado em ./anm.db
```

### Como Inicializar o Banco

```bash
# O banco e criado automaticamente na primeira execucao
python main.py --mode=api

# Ou diretamente via Python
python -c "import asyncio; from db import DatabaseManager; asyncio.run(DatabaseManager().init_db())"
``

### Modos de Execucao

```bash
python main.py --mode=full          # Varredura completa (scraper)
python main.py --mode=ongoing       # Soca animes ongoing
python main.py --mode=jikan-sync    # Atualiza metadados Jikan
python main.py --mode=api           # Inicia FastAPI
python main.py --mode=scheduler     # Inicia APScheduler
python main.py --mode=migrate       # Migra JSON -> SQLite
```

### Como Rodar os Testes

```bash
# Todos os testes
python -m pytest tests/ -v

# Teste especifico
python -m pytest tests/test_db.py -v

# Com cobertura
python -m pytest tests/ -v --tb=short
```

### Estrutura de Testes

- `tests/test_db.py` -- Testes do DatabaseManager (CRUD, paginacao, skip_times)
- `tests/test_cdn.py` -- Testes do CDN checker (URL building, fallback)
- `tests/test_jikan.py` -- Testes do Jikan sync (parsing)
- `tests/test_scheduler.py` -- Testes do scheduler e imports
- `tests/test_aniskip.py` -- Testes do Aniskip (API)

### Convencoes de Codigo

- Usar `async/await` para todas as operacoes de I/O
- Nunca carregar todos os episodios em memória -- usar paginacao
- Tratar erros de rede silenciosamente (logs, nao exceptions)
- Manter compatibilidade com a API existente sempre que possivel

### Pull Requests

1. Fork o repositorio
2. Crie uma branch para sua feature (`git checkout -b feature/nome`)
3. Faca seus commits (`git commit -m 'Adiciona feature X'`)
4. Push para a branch (`git push origin feature/nome`)
5. Abra um Pull Request

### Report de Bugs

Abra uma issue com:
- Descricao do problema
- Passos para reproduzir
- Comportamento esperado vs atual
- Logs (se disponivel)
