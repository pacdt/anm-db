import httpx
import json
import os
import sys
import time

BASE_URL = "http://localhost:8000"
RESULTS_DIR = os.path.dirname(os.path.abspath(__file__))

def save_result(name, data):
    path = os.path.join(RESULTS_DIR, f"{name}.json")
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    return path

def run_tests():
    results = {}
    errors = []
    warnings = []
    passed = 0
    failed = 0

    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:

        # ---- TEST 1: GET / (root) ----
        print("=" * 60)
        print("TEST 1: GET / (root)")
        try:
            r = client.get("/")
            data = r.json()
            results["root"] = {"status": r.status_code, "body": data}
            save_result("01_root", results["root"])
            assert r.status_code == 200, f"Expected 200, got {r.status_code}"
            assert data.get("name") == "anm-db API", f"Missing name field: {data}"
            assert data.get("version") == "2.0.0", f"Missing version field: {data}"
            assert data.get("docs") == "/docs", f"Missing docs field: {data}"
            print(f"  PASS - {r.status_code} | {data}")
            passed += 1
        except Exception as e:
            errors.append(f"root: {e}")
            print(f"  FAIL - {e}")
            failed += 1

        # ---- TEST 2: GET /health ----
        print("=" * 60)
        print("TEST 2: GET /health")
        try:
            r = client.get("/health")
            data = r.json()
            results["health"] = {"status": r.status_code, "body": data}
            save_result("02_health", results["health"])
            assert r.status_code == 200, f"Expected 200, got {r.status_code}"
            assert data.get("status") == "ok", f"Missing status field: {data}"
            print(f"  PASS - {r.status_code} | {data}")
            passed += 1
        except Exception as e:
            errors.append(f"health: {e}")
            print(f"  FAIL - {e}")
            failed += 1

        # ---- TEST 3: GET /animes?limit=2 ----
        print("=" * 60)
        print("TEST 3: GET /animes?limit=2")
        try:
            r = client.get("/animes", params={"limit": 2})
            data = r.json()
            results["animes_limit2"] = {"status": r.status_code, "body": data}
            save_result("03_animes_limit2", results["animes_limit2"])
            assert r.status_code == 200, f"Expected 200, got {r.status_code}"
            assert "items" in data, f"Missing 'items' key: {list(data.keys())}"
            assert "total" in data, f"Missing 'total' key: {list(data.keys())}"
            assert "page" in data, f"Missing 'page' key: {list(data.keys())}"
            assert "pages" in data, f"Missing 'pages' key: {list(data.keys())}"
            assert len(data["items"]) <= 2, f"Expected <=2 items, got {len(data['items'])}"
            print(f"  PASS - {r.status_code} | total={data['total']}, items_returned={len(data['items'])}")
            passed += 1
        except Exception as e:
            errors.append(f"animes_limit2: {e}")
            print(f"  FAIL - {e}")
            failed += 1

        # ---- TEST 4: GET /animes?search=naruto ----
        print("=" * 60)
        print("TEST 4: GET /animes?search=naruto")
        try:
            r = client.get("/animes", params={"search": "naruto"})
            data = r.json()
            results["animes_search"] = {"status": r.status_code, "body": data}
            save_result("04_animes_search", results["animes_search"])
            assert r.status_code == 200, f"Expected 200, got {r.status_code}"
            assert "items" in data, f"Missing 'items' key"
            for item in data["items"]:
                title = item.get("title", "").lower()
                slug = item.get("slug", "").lower()
                assert "naruto" in title or "naruto" in slug, f"Item doesn't match search: {item}"
            print(f"  PASS - {r.status_code} | items={len(data['items'])}, total={data['total']}")
            for item in data["items"]:
                print(f"    -> {item.get('title')} ({item.get('slug')})")
            passed += 1
        except Exception as e:
            errors.append(f"animes_search: {e}")
            print(f"  FAIL - {e}")
            failed += 1

        # ---- TEST 5: GET /animes?status=ongoing ----
        print("=" * 60)
        print("TEST 5: GET /animes?status=ongoing")
        try:
            r = client.get("/animes", params={"status": "ongoing"})
            data = r.json()
            results["animes_ongoing"] = {"status": r.status_code, "body": data}
            save_result("05_animes_ongoing", results["animes_ongoing"])
            assert r.status_code == 200, f"Expected 200, got {r.status_code}"
            print(f"  PASS - {r.status_code} | total={data.get('total', 'N/A')}, items={len(data.get('items', []))}")
            passed += 1
        except Exception as e:
            errors.append(f"animes_ongoing: {e}")
            print(f"  FAIL - {e}")
            failed += 1

        # ---- TEST 6: GET /animes/{slug} ----
        print("=" * 60)
        print("TEST 6: GET /animes/{slug}")
        # First get a real slug from the list
        test_slug = None
        try:
            list_r = client.get("/animes", params={"limit": 5})
            list_data = list_r.json()
            if list_data.get("items"):
                test_slug = list_data["items"][0]["slug"]
                print(f"  Using slug: {test_slug}")
        except Exception as e:
            print(f"  Could not get slug from list: {e}")
            test_slug = "naruto-shippuuden"

        try:
            r = client.get(f"/animes/{test_slug}")
            data = r.json()
            results["anime_detail"] = {"status": r.status_code, "body": data}
            save_result("06_anime_detail", results["anime_detail"])
            assert r.status_code == 200, f"Expected 200, got {r.status_code}"
            assert data.get("slug") == test_slug, f"Slug mismatch: {data.get('slug')} != {test_slug}"
            print(f"  PASS - {r.status_code} | slug={data.get('slug')}")
            print(f"    title: {data.get('titulo_en') or data.get('titulo')}")
            print(f"    type: {data.get('tipo')}")
            print(f"    score: {data.get('score')}")
            print(f"    status: {data.get('status')}")
            print(f"    episodes count: {len(data.get('episodes', []))}")
            print(f"    genres: {data.get('genres', [])}")

            # ---- Verify skip_times is populated ----
            episodes = data.get("episodes", [])
            eps_with_skip = [e for e in episodes if e.get("skip_times") and e["skip_times"] != {}]
            eps_without_skip = [e for e in episodes if not e.get("skip_times") or e["skip_times"] == {}]
            print(f"    episodes with skip_times: {len(eps_with_skip)}/{len(episodes)}")
            if eps_with_skip:
                sample = eps_with_skip[0]
                print(f"      sample skip_times (ep {sample['numero']}): {json.dumps(sample['skip_times'], indent=2)[:200]}")
            if len(eps_without_skip) > 0:
                warnings.append(f"anime_detail({test_slug}): {len(eps_without_skip)}/{len(episodes)} episodes have empty skip_times")
            if len(eps_with_skip) == 0:
                warnings.append(f"anime_detail({test_slug}): NO episodes have skip_times populated!")

            # ---- Verify url_cdn is present ----
            eps_with_cdn = [e for e in episodes if e.get("url_cdn")]
            print(f"    episodes with url_cdn: {len(eps_with_cdn)}/{len(episodes)}")
            if len(eps_with_cdn) == 0:
                warnings.append(f"anime_detail({test_slug}): NO episodes have url_cdn!")

            # ---- Verify fonte_ativa is present ----
            eps_with_fonte = [e for e in episodes if e.get("fonte_ativa")]
            print(f"    episodes with fonte_ativa: {len(eps_with_fonte)}/{len(episodes)}")
            if len(eps_with_fonte) == 0:
                warnings.append(f"anime_detail({test_slug}): NO episodes have fonte_ativa!")

            # ---- Verify genres is not empty ----
            genres = data.get("genres", [])
            assert len(genres) > 0, f"Genres list is empty!"
            print(f"    genres not empty: {len(genres)} genres")
            passed += 1
        except Exception as e:
            errors.append(f"anime_detail({test_slug}): {e}")
            print(f"  FAIL - {e}")
            failed += 1

        # ---- TEST 7: GET /genres ----
        print("=" * 60)
        print("TEST 7: GET /genres")
        try:
            r = client.get("/genres")
            data = r.json()
            results["genres"] = {"status": r.status_code, "body": data}
            save_result("07_genres", results["genres"])
            assert r.status_code == 200, f"Expected 200, got {r.status_code}"
            assert isinstance(data, list), f"Expected list, got {type(data)}"
            assert len(data) > 0, f"Genres list is empty"
            print(f"  PASS - {r.status_code} | {len(data)} genres")
            for g in data[:5]:
                print(f"    -> {g.get('nome')} (count={g.get('count')})")
            if len(data) > 5:
                print(f"    ... and {len(data) - 5} more")
            passed += 1
        except Exception as e:
            errors.append(f"genres: {e}")
            print(f"  FAIL - {e}")
            failed += 1

        # ---- TEST 8: GET /genres/{nome} (real genre) ----
        print("=" * 60)
        print("TEST 8: GET /genres/{nome}")
        test_genre = None
        try:
            genre_r = client.get("/genres")
            genre_data = genre_r.json()
            if genre_data:
                test_genre = genre_data[0]["nome"]
                print(f"  Using genre: {test_genre}")
        except:
            test_genre = "Action"

        try:
            r = client.get(f"/genres/{test_genre}")
            data = r.json()
            results["genre_detail"] = {"status": r.status_code, "body": data}
            save_result("08_genre_detail", results["genre_detail"])
            assert r.status_code == 200, f"Expected 200, got {r.status_code}"
            assert "items" in data, f"Missing 'items' key"
            print(f"  PASS - {r.status_code} | total={data.get('total', 'N/A')}, items={len(data.get('items', []))}")
            passed += 1
        except Exception as e:
            errors.append(f"genre_detail({test_genre}): {e}")
            print(f"  FAIL - {e}")
            failed += 1

        # ---- TEST 9: GET /genres/NonexistentGenre (404) ----
        print("=" * 60)
        print("TEST 9: GET /genres/NonexistentGenre (should 404)")
        try:
            r = client.get("/genres/NonexistentGenre999")
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"text": r.text}
            results["genre_404"] = {"status": r.status_code, "body": data}
            save_result("09_genre_404", results["genre_404"])
            assert r.status_code == 404, f"Expected 404, got {r.status_code}"
            print(f"  PASS - {r.status_code} | {data}")
            passed += 1
        except Exception as e:
            errors.append(f"genre_404: {e}")
            print(f"  FAIL - {e}")
            failed += 1

        # ---- TEST 10: GET /episodes/latest?limit=3 ----
        print("=" * 60)
        print("TEST 10: GET /episodes/latest?limit=3")
        try:
            r = client.get("/episodes/latest", params={"limit": 3})
            data = r.json()
            results["episodes_latest"] = {"status": r.status_code, "body": data}
            save_result("10_episodes_latest", results["episodes_latest"])
            assert r.status_code == 200, f"Expected 200, got {r.status_code}"
            assert isinstance(data, list), f"Expected list, got {type(data)}"
            assert len(data) <= 3, f"Expected <=3 items, got {len(data)}"
            print(f"  PASS - {r.status_code} | {len(data)} episodes")
            for ep in data:
                print(f"    -> anime={ep.get('slug')}, ep={ep.get('numero')}, fonte={ep.get('fonte_ativa')}")
            passed += 1
        except Exception as e:
            errors.append(f"episodes_latest: {e}")
            print(f"  FAIL - {e}")
            failed += 1

        # ---- TEST 11: GET /episodes/{slug} ----
        print("=" * 60)
        print("TEST 11: GET /episodes/{slug}")
        eps_slug = test_slug  # reuse slug from test 6
        try:
            r = client.get(f"/episodes/{eps_slug}", params={"limit": 5})
            data = r.json()
            results["episodes_by_slug"] = {"status": r.status_code, "body": data}
            save_result("11_episodes_by_slug", results["episodes_by_slug"])
            assert r.status_code == 200, f"Expected 200, got {r.status_code}"
            assert "items" in data, f"Missing 'items' key"
            print(f"  PASS - {r.status_code} | total={data.get('total', 'N/A')}, items={len(data.get('items', []))}")

            # Verify skip_times per episode
            eps_list = data.get("items", [])
            eps_with_skip = [e for e in eps_list if e.get("skip_times") and e["skip_times"] != {}]
            eps_with_cdn = [e for e in eps_list if e.get("url_cdn")]
            print(f"    episodes with skip_times: {len(eps_with_skip)}/{len(eps_list)}")
            print(f"    episodes with url_cdn: {len(eps_with_cdn)}/{len(eps_list)}")

            if eps_with_skip:
                sample = eps_with_skip[0]
                print(f"      sample skip_times (ep {sample['numero']}): {json.dumps(sample['skip_times'], indent=2)[:200]}")
            if len(eps_with_skip) == 0:
                warnings.append(f"episodes_by_slug({eps_slug}): NO episodes have skip_times populated!")
            if len(eps_with_cdn) == 0:
                warnings.append(f"episodes_by_slug({eps_slug}): NO episodes have url_cdn!")
            passed += 1
        except Exception as e:
            errors.append(f"episodes_by_slug({eps_slug}): {e}")
            print(f"  FAIL - {e}")
            failed += 1

        # ---- TEST 12: GET /animes/{slug} nonexistent (404) ----
        print("=" * 60)
        print("TEST 12: GET /animes/{slug} nonexistent (should 404)")
        try:
            r = client.get("/animes/nonexistent-anime-99999")
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"text": r.text}
            results["anime_404"] = {"status": r.status_code, "body": data}
            save_result("12_anime_404", results["anime_404"])
            assert r.status_code == 404, f"Expected 404, got {r.status_code}"
            print(f"  PASS - {r.status_code} | {data}")
            passed += 1
        except Exception as e:
            errors.append(f"anime_404: {e}")
            print(f"  FAIL - {e}")
            failed += 1

        # ---- TEST 13: GET /episodes/{slug} nonexistent (404) ----
        print("=" * 60)
        print("TEST 13: GET /episodes/{slug} nonexistent (should 404)")
        try:
            r = client.get("/episodes/nonexistent-anime-99999")
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"text": r.text}
            results["episodes_404"] = {"status": r.status_code, "body": data}
            save_result("13_episodes_404", results["episodes_404"])
            assert r.status_code == 404, f"Expected 404, got {r.status_code}"
            print(f"  PASS - {r.status_code} | {data}")
            passed += 1
        except Exception as e:
            errors.append(f"episodes_404: {e}")
            print(f"  FAIL - {e}")
            failed += 1

        # ---- TEST 14: Pagination edge case ----
        print("=" * 60)
        print("TEST 14: GET /animes page=999 (empty)")
        try:
            r = client.get("/animes", params={"page": 999})
            data = r.json()
            results["animes_empty_page"] = {"status": r.status_code, "body": data}
            save_result("14_animes_empty_page", results["animes_empty_page"])
            assert r.status_code == 200, f"Expected 200, got {r.status_code}"
            assert len(data.get("items", [])) == 0, f"Expected empty items on page 999"
            print(f"  PASS - {r.status_code} | items={len(data.get('items', []))}")
            passed += 1
        except Exception as e:
            errors.append(f"animes_empty_page: {e}")
            print(f"  FAIL - {e}")
            failed += 1

    # ---- SUMMARY ----
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Warnings: {len(warnings)}")

    if warnings:
        print("\nWARNINGS:")
        for w in warnings:
            print(f"  - {w}")

    if errors:
        print("\nERRORS:")
        for e in errors:
            print(f"  - {e}")

    # Save summary
    summary = {
        "passed": passed,
        "failed": failed,
        "warnings": warnings,
        "errors": errors,
        "results": {k: {"status": v["status"]} for k, v in results.items()},
    }
    save_result("00_summary", summary)

    return failed == 0

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
