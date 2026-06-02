# anm-db Architecture (v2.0)

Camadas do projeto, da borda (API) até o storage.

```
┌─────────────────────────────────────────────────────────────┐
│  api/        FastAPI + uvicorn                               │
│  ├── routes/  animes, episodes, genres, download            │
│  ├── schemas  Pydantic models + pick_lang() helper          │
│  └── deps     DatabaseManager singleton (lifespan)          │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│  services/   Orquestracao de dominio (nao HTTP)             │
│  ├── translator         AnimeTranslator (Gemini PT-BR)      │
│  ├── missing_scanner    MissingEpisodeScanner               │
│  └── downloader         VideoDownloader (ffmpeg pipe)       │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│  scrapers/   Coleta externa (HTTP)                           │
│  ├── jikan               JikanSync (snapshot completo)      │
│  ├── cdn                 check_cdn_episode (HLS .m3u8)      │
│  ├── aniskip             fetch_skip_times                    │
│  ├── animefire           AnimeScraper (driver principal)    │
│  ├── blogger             resolve_blogger_url                │
│  ├── gemini              GeminiClient (PT-BR)               │
│  └── genre_translator    mapa estatico PT-BR                 │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│  repository/ Camada de persistencia                          │
│  └── database    DatabaseManager (aiosqlite + WAL)           │
│                  SCHEMA_SQL + MIGRATIONS dict               │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│  domain/     Entidades imutaveis                             │
│  ├── Anime, Episodio, Genero, SkipTime, JikanMetadata,      │
│  └── TranslationLog, JobRun                                 │
└─────────────────────────────────────────────────────────────┘
```

## Fluxos principais

### 1. Scraping (`main.py --mode=full|ongoing`)
```
AnimeScraper.atualizar_anime(slug, tipo)
  ├─ cdn_checker.check_cdn_episode()      -> URL HLS
  ├─ animefire.scrape_episode_list()      -> URLs Blogger
  ├─ blogger.resolve_blogger_url()        -> URL MP4 real
  └─ DB.upsert_episodio() com fonte_ativa

APSJob 07:00 UTC: episode_scan -> get_ongoing_due() -> scraper
```

### 2. Traducao PT-BR
```
main.py --mode=translate  ou  APSJob 03:00 dom
  AnimeTranslator.translate_pending()
    ├─ DB.list_animes_pending_translation()   # WHERE titulo_pt IS NULL
    ├─ GeminiClient.translate_batch(10)        # 10 animes/request
    ├─ DB.upsert_anime()  com COALESCE(?, titulo_pt)  # nao sobrescreve
    └─ DB.log_translation() em translation_log
```

### 3. Download com ffmpeg pipe
```
GET /download/{slug}/{n}?source=auto&format=mp4
  VideoDownloader.resolve()         -> DownloadResult(url, source_used)
  VideoDownloader.stream(result, format)
    ├─ HLS + ffmpeg disponivel  -> subprocess ffmpeg -c copy -bsf:v h264_mp4toannexb
    ├─ MP4 direto               -> aiohttp stream
    └─ ffmpeg falhou            -> fallback HLS cru
```

## Decisoes de design

- **Schema versioning**: `SCHEMA_VERSION=2`, `MIGRATIONS: dict[int, list[str]]` permite upgrade
  incremental sem perder dados. Fresh DBs ja vem com v2.
- **Settings via pydantic-settings**: type-safe, lazy via `get_settings()` (singleton com
  `@lru_cache`). Carrega `.env` automaticamente.
- **Translator idempotente**: `WHERE (titulo_pt IS NULL OR sinopse_pt IS NULL) AND
  (traduzido_em IS NULL OR updated_at > traduzido_em)` evita retrabalho.
- **Genre PT-BR via mapa estatico**: zero chamadas Gemini, lookup O(1), fallback para
  nome original. 21 generos principais + 5 demographics + 50+ themes.
- **Download sem disco**: `ffmpeg -c copy` no pipe (`pipe:1`) evita temp files. Baixo CPU
  porque so remuxa (sem reencodar).
- **i18n via query param `?lang=`**: cliente controla o idioma. PT-BR como padrao
  (recurso de produto).
- **Camadas com fronteira clara**: domain nao importa de repository/repository nao
  importa de scrapers. Services orquestram domain + scrapers + repository.

## Configuracao (.env)

```env
DB_PATH=anm.db
GEMINI_API_KEY=<sua-chave>
GEMINI_MODEL=gemini-2.5-flash
GEMINI_RPM=15
GEMINI_RPD=1500
TRANSLATION_BATCH_SIZE=10
TRANSLATION_ENABLED=true
CONCURRENCY_EPISODIOS=3
FFMPEG_PATH=ffmpeg
```

Veja `docs/API.md` para referencia completa de endpoints.
