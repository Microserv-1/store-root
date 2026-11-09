"""Reproducible authenticated closed-loop load; outputs measurements, not HPA claims."""
import argparse
import concurrent.futures
import collections
import json
import os
from pathlib import Path
import statistics
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid

parser = argparse.ArgumentParser()
parser.add_argument("--base-url", default="http://127.0.0.1:8080")
parser.add_argument("--users", type=int, default=4)
parser.add_argument("--duration", type=int, default=60)
parser.add_argument("--scenario", choices=["identity", "login"], default="identity")
parser.add_argument("--output", default="artifacts/load.json")
args = parser.parse_args()
if not 1 <= args.users <= 100 or args.duration < 1:
    parser.error("users must be 1..100 and duration positive")
credentials = {"email": f"load-{uuid.uuid4().hex}@example.com", "password": "load-test-Password123!"}
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

def request(method, path, payload=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(args.base_url+path, data=json.dumps(payload).encode() if payload else None, headers=headers, method=method)
    try:
        response = opener.open(req, timeout=15)
    except urllib.error.HTTPError as e:
        response = e
    with response:
        return response.status, response.read(), response.headers.get("X-Served-By", "unknown")

assert request("POST", "/accounts", {"name": "Load", **credentials})[0] == 201
status, body, _ = request("POST", "/auth/login", credentials)
assert status == 200, body
token = json.loads(body)["access_token"]
stop = time.monotonic() + args.duration
samples, statuses, instances = [], collections.Counter(), collections.Counter()
lock = threading.Lock()
started = time.monotonic()

def worker():
    while time.monotonic() < stop:
        begin = time.monotonic()
        try:
            if args.scenario == "login":
                status, _, instance = request("POST", "/auth/login", credentials)
            else:
                status, _, instance = request("GET", "/accounts/me", token=token)
        except (OSError, TimeoutError):
            status, instance = 0, "connection-error"
        elapsed = (time.monotonic()-begin)*1000
        with lock:
            samples.append(elapsed); statuses[status]+=1; instances[instance]+=1

with concurrent.futures.ThreadPoolExecutor(max_workers=args.users) as pool:
    list(pool.map(lambda _: worker(), range(args.users)))
elapsed = time.monotonic()-started
ordered = sorted(samples)
def percentile(p):
    return ordered[min(len(ordered)-1, int((len(ordered)-1)*p))] if ordered else None
def revision(path):
    return subprocess.check_output(["git", "-C", path, "rev-parse", "HEAD"], text=True).strip()
def dirty(path):
    return bool(subprocess.check_output(["git", "-C", path, "status", "--porcelain"], text=True).strip())
result = {"timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "scenario": args.scenario, "model": "closed-loop, no think time", "base_url": args.base_url,
    "users": args.users, "requested_duration_s": args.duration, "actual_duration_s": round(elapsed,3),
    "requests": len(samples), "requests_per_second": round(len(samples)/elapsed,3),
    "latency_ms": {"p50": percentile(.50), "p95": percentile(.95), "p99": percentile(.99)},
    "status_counts": dict(statuses), "error_ratio": sum(n for code,n in statuses.items() if not 200<=code<300)/max(1,len(samples)),
    "upstream_instances": dict(instances), "commits": {s:revision("api/"+s) for s in ("account","auth","gateway")},
    "dirty": {s:dirty("api/"+s) for s in ("account","auth","gateway")},
    "note": "Record replicas, CPU/memory, image IDs and environment alongside this report. Dirty source is not identified by HEAD alone."}
output = Path(args.output); output.parent.mkdir(parents=True,exist_ok=True)
output.write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
