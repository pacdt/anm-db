"""Bateria completa de testes de endpoints."""
import json
import sys
import time
import httpx

BASE = "http://localhost:8000"
results = []
errors_found = []


def test(name, method, path, expect_status=200, **kwargs):
    t0 = time.perf_counter()
    try:
        with httpx.Client(timeout=10.0) as c:
            r = c.request(method, f"{BASE}{path}", **kwargs)
        elapsed = (time.perf_counter() - t0) * 1000
        ok = r.status_code == expect_status
        status = "PASS" if ok else "FAIL"
        snippet = r.text[:160].replace("\n", " ")
        results.append({
            "endpoint": f"{method} {path}",
            "status": status,
            "http": r.status_code,
            "expected": expect_status,
            "ms": round(elapsed, 1),
            "len": len(r.text),
            "snippet": snippet,
        })
        if not ok:
            errors_found.append({
                "endpoint": f"{method} {path}",
                "http": r.status_code,
                "expected": expect_status,
                "body": r.text[:500],
            })
        return r
    except Exception as e:
        elapsed = (time.perf_counter() - t0) * 1000
        results.append({
            "endpoint": f"{method} {path}",
            "status": "ERROR",
            "http": "-",
            "expected": expect_status,
            "ms": round(elapsed, 1),
            "len": 0,
            "snippet": str(e)[:160],
        })
        errors_found.append({
            "endpoint": f"{method} {path}",
            "http": "EXC",
            "expected": expect_status,
            "body": str(e),
        })
        return None


# 1. Info / health
r = test("root", "GET", "/")
r = test("health", "GET", "/health")

# 2. Animes - listagem
test("animes_page1", "GET", "/animes?page=1&limit=5")
test("animes_page2", "GET", "/animes?page=2&limit=5")
test("animes_limit_max", "GET", "/animes?page=1&limit=100")
test("animes_limit_overflow", "GET", "/animes?page=1&limit=500", expect_status=422)

# 3. Animes - filtros
r = test("animes_search_naruto", "GET", "/animes?search=naruto")
r = test("animes_search_xyz", "GET", "/animes?search=xyz_nonexistent_12345")
test("animes_status_ongoing", "GET", "/animes?status=ongoing&limit=3")
test("animes_status_finished", "GET", "/animes?status=finished&limit=3")
test("animes_invalid_status", "GET", "/animes?status=invalid", expect_status=422)

# 4. Pega primeiro slug do result para testes seguintes
r_data = None
with httpx.Client(timeout=10.0) as c:
    rr = c.get(f"{BASE}/animes?page=1&limit=1")
    if rr.status_code == 200:
        try:
            r_data = rr.json()
        except Exception:
            r_data = None
slug = None
if r_data:
    items = r_data.get("items") if isinstance(r_data, dict) else r_data
    if isinstance(items, list) and items:
        slug = items[0].get("slug")

# 5. Animes - detalhe
if slug:
    test("anime_detail_valid", "GET", f"/animes/{slug}")
test("anime_detail_404", "GET", "/animes/this-slug-does-not-exist-zzz", expect_status=404)
test("anime_detail_special_chars", "GET", "/animes/a%20b%20c", expect_status=404)

# 6. Gêneros
test("genres_list", "GET", "/genres")
test("genres_404", "GET", "/genres/GeneroQueNaoExiste", expect_status=404)

# 7. Episódios
test("episodes_latest", "GET", "/episodes/latest?limit=10")
test("episodes_latest_limit_overflow", "GET", "/episodes/latest?limit=999999", expect_status=422)
if slug:
    test("episodes_latest_by_anime", "GET", f"/episodes/latest?anime={slug}&limit=5")
test("episodes_latest_invalid_anime", "GET", "/episodes/latest?anime=nao-existe")

# 8. OpenAPI / docs
test("openapi", "GET", "/openapi.json")
test("docs", "GET", "/docs")
test("redoc", "GET", "/redoc")

# 9. Download (negativos primeiro; slug inexistente -> 404)
test("download_404", "GET", "/download/this-anime-does-not-exist/1", expect_status=404)

# 10. Resumo
print("\n" + "=" * 100)
print(f"ENDPOINT TEST RESULTS  ({len(results)} total)")
print("=" * 100)
for r in results:
    badge = {"PASS": "[OK]", "FAIL": "[FAIL]", "ERROR": "[ERR]"}[r["status"]]
    print(f"{badge} {r['status']:5s} {r['http']!s:5s}  {r['ms']:>7.1f}ms  {r['endpoint']}")

passed = sum(1 for r in results if r["status"] == "PASS")
failed = sum(1 for r in results if r["status"] in ("FAIL", "ERROR"))
print("-" * 100)
print(f"Passed: {passed}  Failed: {failed}  Total: {len(results)}")

if errors_found:
    print("\n" + "=" * 100)
    print("ERRORS DETAIL")
    print("=" * 100)
    for e in errors_found:
        print(f"\n[{e['http']} != {e['expected']}] {e['endpoint']}")
        print(f"  {e['body'][:300]}")

sys.exit(0 if failed == 0 else 1)
