"""Reproducible authenticated closed-loop load across all 6 services; outputs measurements."""
import argparse
import collections
import concurrent.futures
import json
from pathlib import Path
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid

SCENARIOS = [
    "identity",
    "login",
    "products_cached",
    "products_uncached",
    "orders",
    "exchange",
    "business_mix",
]

parser = argparse.ArgumentParser()
parser.add_argument("--base-url", default="http://127.0.0.1:8080")
parser.add_argument("--users", type=int, default=4)
parser.add_argument("--duration", type=int, default=60)
parser.add_argument("--scenario", choices=SCENARIOS, default="identity")
parser.add_argument("--output", default="artifacts/load.json")
args = parser.parse_args()
if not 1 <= args.users <= 100 or args.duration < 1:
    parser.error("users must be 1..100 and duration positive")

credentials = {"email": f"load-{uuid.uuid4().hex}@example.com", "password": "load-test-Password123!"}
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def request(method, path, payload=None, token=None, extra_headers=None):
    headers = {"Content-Type": "application/json", **(extra_headers or {})}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(
        args.base_url + path,
        data=json.dumps(payload).encode() if payload else None,
        headers=headers,
        method=method,
    )
    try:
        response = opener.open(req, timeout=15)
    except urllib.error.HTTPError as e:
        response = e
    with response:
        return (
            response.status,
            response.read(),
            response.headers.get("X-Served-By", "unknown"),
            response.headers.get("X-Cache", "NONE"),
        )


assert request("POST", "/accounts", {"name": "Load", **credentials})[0] == 201
status, body, _, _ = request("POST", "/auth/login", credentials)
assert status == 200, body
token = json.loads(body)["access_token"]

seeded_product_id = None
if args.scenario in ("products_cached", "products_uncached", "orders", "business_mix"):
    status, pbody, _, _ = request(
        "POST",
        "/products",
        {"name": f"Load Product {uuid.uuid4().hex[:6]}", "price": 49.90, "unit": "unit"},
        token=token,
    )
    assert status == 201, pbody
    seeded_product_id = json.loads(pbody)["id"]
    # Warm up cache for product detail and catalog
    request("GET", f"/products/{seeded_product_id}", token=token)
    request("GET", "/products", token=token)

stop = time.monotonic() + args.duration
samples = []
statuses = collections.Counter()
instances = collections.Counter()
cache_hits = collections.Counter()
lock = threading.Lock()
started = time.monotonic()


def worker(worker_idx):
    seq = worker_idx
    while time.monotonic() < stop:
        begin = time.monotonic()
        seq += 1
        try:
            if args.scenario == "login":
                status, _, instance, xcache = request("POST", "/auth/login", credentials)
            elif args.scenario == "identity":
                status, _, instance, xcache = request("GET", "/accounts/me", token=token)
            elif args.scenario == "products_cached":
                status, _, instance, xcache = request("GET", f"/products/{seeded_product_id}", token=token)
            elif args.scenario == "products_uncached":
                status, _, instance, xcache = request(
                    "GET",
                    f"/products/{seeded_product_id}?cache=bypass",
                    token=token,
                    extra_headers={"X-Cache-Control": "no-cache"},
                )
            elif args.scenario == "exchange":
                status, _, instance, xcache = request("GET", "/exchanges/USD/BRL", token=token)
            elif args.scenario == "orders":
                status, _, instance, xcache = request(
                    "POST",
                    "/orders",
                    {"items": [{"idProduct": seeded_product_id, "quantity": 1}]},
                    token=token,
                )
            elif args.scenario == "business_mix":
                mod = seq % 5
                if mod in (0, 1):
                    status, _, instance, xcache = request("GET", f"/products/{seeded_product_id}", token=token)
                elif mod == 2:
                    status, _, instance, xcache = request("GET", "/products", token=token)
                elif mod == 3:
                    status, _, instance, xcache = request("GET", "/exchanges/USD/BRL", token=token)
                else:
                    status, _, instance, xcache = request(
                        "POST",
                        "/orders",
                        {"items": [{"idProduct": seeded_product_id, "quantity": 1}]},
                        token=token,
                    )
        except (OSError, TimeoutError):
            status, instance, xcache = 0, "connection-error", "ERROR"
        elapsed = (time.monotonic() - begin) * 1000
        with lock:
            samples.append(elapsed)
            statuses[status] += 1
            instances[instance] += 1
            cache_hits[xcache] += 1


with concurrent.futures.ThreadPoolExecutor(max_workers=args.users) as pool:
    list(pool.map(worker, range(args.users)))
elapsed = time.monotonic() - started
ordered = sorted(samples)


def percentile(p):
    return round(ordered[min(len(ordered) - 1, int((len(ordered) - 1) * p))], 3) if ordered else None


def revision(path):
    return subprocess.check_output(["git", "-C", path, "rev-parse", "HEAD"], text=True).strip()


def dirty(path):
    return bool(subprocess.check_output(["git", "-C", path, "status", "--porcelain"], text=True).strip())


services = tuple(s for s in ("account", "auth", "gateway", "product", "order", "exchange") if Path("api/" + s).exists())

result = {
    "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "scenario": args.scenario,
    "model": "closed-loop, no think time",
    "base_url": args.base_url,
    "users": args.users,
    "requested_duration_s": args.duration,
    "actual_duration_s": round(elapsed, 3),
    "requests": len(samples),
    "requests_per_second": round(len(samples) / elapsed, 3),
    "latency_ms": {"p50": percentile(0.50), "p95": percentile(0.95), "p99": percentile(0.99)},
    "status_counts": dict(statuses),
    "x_cache_counts": dict(cache_hits),
    "error_ratio": sum(n for code, n in statuses.items() if not 200 <= code < 300) / max(1, len(samples)),
    "upstream_instances": dict(instances),
    "commits": {s: revision("api/" + s) for s in services},
    "dirty": {s: dirty("api/" + s) for s in services},
    "note": "Record replicas, CPU/memory, image IDs and environment alongside this report. Dirty source is not identified by HEAD alone.",
}
output = Path(args.output)
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
