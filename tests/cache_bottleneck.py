"""Benchmark and functional proof of Gargalo B1: Redis Cache-Aside in Product Service."""
import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import statistics
import time
import urllib.error
import urllib.request
import uuid

parser = argparse.ArgumentParser()
parser.add_argument("--base-url", default=os.environ.get("BASE_URL", "http://127.0.0.1:8080"))
parser.add_argument("--users", type=int, default=8)
parser.add_argument("--requests-per-phase", type=int, default=240)
parser.add_argument("--output", default="artifacts/cache-bottleneck.json")
args = parser.parse_args()

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def request(method, path, payload=None, token=None, extra_headers=None):
    headers = {"Content-Type": "application/json", **(extra_headers or {})}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        args.base_url + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers=headers,
        method=method,
    )
    try:
        resp = opener.open(req, timeout=15)
    except urllib.error.HTTPError as err:
        resp = err
    with resp:
        raw = resp.read()
        body = json.loads(raw) if raw else None
        hdrs = {k.lower(): v for k, v in resp.headers.items()}
        return resp.status, body, hdrs


def percentile(ordered, p):
    if not ordered:
        return None
    idx = min(len(ordered) - 1, int((len(ordered) - 1) * p))
    return round(ordered[idx], 3)


def run_phase(path, token, bypass_cache=False):
    extra = {"X-Cache-Control": "no-cache"} if bypass_cache else {}
    target_path = (path + ("&" if "?" in path else "?") + "cache=bypass") if bypass_cache else path
    latencies = []
    cache_headers = {}
    statuses = {}
    started = time.monotonic()

    def one_call(_):
        t0 = time.monotonic()
        status, _, hdrs = request("GET", target_path, token=token, extra_headers=extra)
        dt = (time.monotonic() - t0) * 1000.0
        return status, dt, hdrs.get("x-cache", "NONE")

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.users) as pool:
        for status, dt, xcache in pool.map(one_call, range(args.requests_per_phase)):
            latencies.append(dt)
            statuses[str(status)] = statuses.get(str(status), 0) + 1
            cache_headers[xcache] = cache_headers.get(xcache, 0) + 1

    elapsed = time.monotonic() - started
    ordered = sorted(latencies)
    return {
        "mode": "uncached_db_bypass" if bypass_cache else "redis_cache_aside",
        "requests": len(latencies),
        "concurrency": args.users,
        "duration_s": round(elapsed, 3),
        "requests_per_second": round(len(latencies) / max(elapsed, 0.001), 2),
        "latency_ms": {
            "avg": round(statistics.mean(ordered), 3),
            "p50": percentile(ordered, 0.50),
            "p95": percentile(ordered, 0.95),
            "p99": percentile(ordered, 0.99),
        },
        "x_cache_counts": cache_headers,
        "status_counts": statuses,
    }


def main():
    email = f"cache-bench-{uuid.uuid4().hex[:8]}@example.com"
    password = "bench-Password123!"
    status, _, _ = request("POST", "/accounts", {"name": "Cache Bench", "email": email, "password": password})
    assert status == 201
    status, session, _ = request("POST", "/auth/login", {"email": email, "password": password})
    assert status == 200
    token = session["access_token"]

    # Seed catalog items so catalog queries carry realistic payload
    created_ids = []
    for idx in range(15):
        status, prod, _ = request(
            "POST",
            "/products",
            {
                "name": f"Catalog Item {idx}-{uuid.uuid4().hex[:6]}",
                "price": round(19.90 + idx * 7.5, 2),
                "unit": "unit",
                "stock": 50 + idx,
            },
            token=token,
        )
        assert status == 201
        created_ids.append(prod["id"])

    target_id = created_ids[0]

    # 1. Verify MISS -> HIT on catalog list after write, and immediate invalidation on DELETE
    status, temp, _ = request(
        "POST",
        "/products",
        {"name": "Invalidate Target", "price": 55.0, "unit": "unit", "stock": 10},
        token=token,
    )
    assert status == 201
    _, _, h_miss = request("GET", "/products", token=token)
    _, _, h_hit = request("GET", "/products", token=token)
    _, _, detail_hit = request("GET", f"/products/{temp['id']}", token=token)
    del_status, _, _ = request("DELETE", f"/products/{temp['id']}", token=token)
    after_del_status, _, _ = request("GET", f"/products/{temp['id']}", token=token)
    assert h_miss.get("x-cache") == "MISS", h_miss
    assert h_hit.get("x-cache") == "HIT", h_hit
    assert detail_hit.get("x-cache") == "HIT", detail_hit
    assert del_status == 204 and after_del_status == 404

    # Warm up cache for target product and catalog list
    request("GET", f"/products/{target_id}", token=token)
    request("GET", "/products", token=token)

    # 2. Benchmark uncached (DB bypass) vs cached (Redis HIT)
    detail_uncached = run_phase(f"/products/{target_id}", token, bypass_cache=True)
    detail_cached = run_phase(f"/products/{target_id}", token, bypass_cache=False)
    list_uncached = run_phase("/products", token, bypass_cache=True)
    list_cached = run_phase("/products", token, bypass_cache=False)

    _, stats_after, _ = request("GET", "/products/cache/stats", token=token)

    report = {
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "bottleneck": "B1 - Redis Cache-Aside on Product Service",
        "base_url": args.base_url,
        "functional_checks": {
            "first_read_x_cache": h_miss.get("x-cache"),
            "second_read_x_cache": h_hit.get("x-cache"),
            "delete_status": del_status,
            "read_after_delete_status": after_del_status,
        },
        "benchmarks": {
            "product_detail": {
                "uncached": detail_uncached,
                "cached": detail_cached,
                "rps_speedup_ratio": round(
                    detail_cached["requests_per_second"] / max(detail_uncached["requests_per_second"], 0.01), 2
                ),
                "p95_reduction_pct": round(
                    (1.0 - (detail_cached["latency_ms"]["p95"] / max(detail_uncached["latency_ms"]["p95"], 0.001)))
                    * 100.0,
                    2,
                ),
            },
            "product_list": {
                "uncached": list_uncached,
                "cached": list_cached,
                "rps_speedup_ratio": round(
                    list_cached["requests_per_second"] / max(list_uncached["requests_per_second"], 0.01), 2
                ),
                "p95_reduction_pct": round(
                    (1.0 - (list_cached["latency_ms"]["p95"] / max(list_uncached["latency_ms"]["p95"], 0.001)))
                    * 100.0,
                    2,
                ),
            },
        },
        "service_cache_stats": stats_after,
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
