======================================================================
  ANM-DB API ENDPOINT TEST REPORT
  Generated: 2026-05-31
======================================================================

[PASS] Root endpoint
  Endpoint: GET /
  HTTP Status: 200
  Details: Returns API name='anm-db API', version='2.0.0', docs='/docs'

[PASS] Health check
  Endpoint: GET /health
  HTTP Status: 200
  Details: Returns {status: ok}

[PASS] Animes list (limit=2)
  Endpoint: GET /animes?limit=2
  HTTP Status: 200
  Details: Returns paginated response with items[], total=5166, page=1, limit=2, pages=2583

[PASS] Animes search
  Endpoint: GET /animes?search=naruto
  HTTP Status: 200
  Details: Returns 7 results including naruto-dublado, naruto-shippuuden-dublado, etc.

[PASS] Animes ongoing
  Endpoint: GET /animes?status=ongoing
  HTTP Status: 200
  Details: Returns total=10 ongoing animes

[PASS] Anime detail (naruto-dublado)
  Endpoint: GET /animes/naruto-dublado
  HTTP Status: 200
  Details: Returns full anime with titulo='Naruto (Dublado)', genres=['Action','Fantasy','Adventure'], 211 episodes
  Issues:
    - skip_times: ALL empty {} on all 211 episodes
    - url_cdn: ALL None on all episodes (fonte_ativa=animefire)
    - Field names differ from expected: uses 'titulo' not 'title', 'imagem' not 'image'

[PASS] Genres list
  Endpoint: GET /genres
  HTTP Status: 200
  Details: Returns flat array of 21 genres (Action, Adventure, Avant Garde, etc.)

[PASS] Genre detail (Action)
  Endpoint: GET /genres/Action
  HTTP Status: 200
  Details: Returns paginated response with items[], total, page, limit, pages
  Issues:
    - Genre name field is missing (nome=None) in response
    - Returns paginated anime list for the genre

[PASS] Episodes latest
  Endpoint: GET /episodes/latest?limit=3
  HTTP Status: 200
  Details: Returns 3 episodes from zenshuu-dublado (eps 10-12)
  Issues:
    - skip_times: ALL empty {}
    - url_cdn: Present for all 3 episodes (cdn source)
    - fonte_ativa: 'cdn' for all 3 episodes

[PASS] Episodes by slug (naruto-dublado)
  Endpoint: GET /episodes/naruto-dublado
  HTTP Status: 200
  Details: Returns paginated response with 50 episodes per page
  Issues:
    - skip_times: ALL empty {}
    - url_cdn: ALL None (fonte_ativa=animefire)

[PASS] Anime detail CDN (zenshuu-dublado)
  Endpoint: GET /animes/zenshuu-dublado
  HTTP Status: 200
  Details: Returns anime with titulo='Zenshuu. (Dublado)', genres=['Action','Fantasy'], 11 episodes
  Issues:
    - skip_times: ALL empty {} even for CDN episodes
    - url_cdn: False on anime detail eps (despite episodes/latest showing cdn URLs)
    - Inconsistency: /episodes/latest shows url_cdn for same anime, but /animes/{slug} does not

[PASS] Nonexistent anime
  Endpoint: GET /animes/nonexistent-slug-12345
  HTTP Status: 404
  Details: Correctly returns 404

[PASS] Nonexistent episodes
  Endpoint: GET /episodes/nonexistent-slug-12345
  HTTP Status: 404
  Details: Correctly returns 404

[FAIL] Nonexistent genre
  Endpoint: GET /genres/NonexistentGenre
  HTTP Status: 200
  Details: Returns 200 with empty items[] instead of 404
  Issues:
    - Should return 404 for non-existent genre, currently returns 200 with empty results

======================================================================
  SUMMARY
======================================================================
  Total tests: 14
  Passed: 13
  Failed: 1

======================================================================
  CRITICAL FINDINGS
======================================================================

  1. SKIP_TIMES: Empty {} across ALL endpoints and ALL episodes.
     - The aniskip module may not be populating the DB correctly.
     - Even CDN-sourced episodes lack skip_times data.

  2. URL_CDN INCONSISTENCY:
     - /episodes/latest returns url_cdn for CDN episodes.
     - /animes/{slug} returns url_cdn=None for the SAME episodes.
     - /episodes/{slug} returns url_cdn=None for animefire episodes.
     - The anime detail endpoint episode serialization differs
       from the episodes list endpoint serialization.

  3. FONTE_ATIVA DISTRIBUTION:
     - Most episodes have fonte_ativa='animefire' (no CDN URL).
     - Only /episodes/latest returns CDN episodes with url_cdn.
     - CDN episodes exist but are only surfaced via latest endpoint.

  4. MISSING FIELD MAPPING:
     - Anime detail uses 'titulo' not 'title', 'imagem' not 'image'.
     - Genre detail returns nome=None (missing genre name in response).

  5. ERROR HANDLING:
     - /genres/{nonexistent} returns 200 with empty list instead of 404.
     - /animes/{nonexistent} and /episodes/{nonexistent} correctly return 404.

  FILES SAVED: test_results/ directory (14 JSON files)
======================================================================