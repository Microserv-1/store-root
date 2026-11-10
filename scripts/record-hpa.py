"""Record live kubectl output and a real concurrent load run, without desktop capture."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

parser = argparse.ArgumentParser()
parser.add_argument("--context", default="kind-microserv-store")
parser.add_argument("--base-url", default="http://127.0.0.1:8082")
parser.add_argument("--duration", type=int, default=60)
parser.add_argument("--users", type=int, default=8)
parser.add_argument("--scenario", default="business_mix")
parser.add_argument("--snapshot-output", default="artifacts/recorded-hpa.json")
parser.add_argument("--load-output", default="artifacts/k8s-business-mix.json")
parser.add_argument("--video-output", default="artifacts/hpa-evidence.mp4")
args = parser.parse_args()

output = Path("artifacts")
output.mkdir(exist_ok=True)
live = output / "live-hpa.txt"
live.write_text("Starting live Kubernetes evidence...", encoding="utf-8")
load = None
loadlog = (output / "recorded-load.log").open("w")
started = time.monotonic()
snapshots = []
base = ["kubectl", "--context", args.context, "-n", "store"]
try:
    while time.monotonic() - started < args.duration + 18:
        elapsed = time.monotonic() - started
        if elapsed >= 6 and load is None:
            load = subprocess.Popen(
                [
                    sys.executable,
                    "scripts/load.py",
                    "--base-url",
                    args.base_url,
                    "--users",
                    str(args.users),
                    "--duration",
                    str(args.duration),
                    "--scenario",
                    args.scenario,
                    "--output",
                    args.load_output,
                ],
                stdout=loadlog,
                stderr=loadlog,
            )
        status = (
            "BASELINE"
            if load is None
            else ("RUNNING" if load.poll() is None else f"FINISHED (exit {load.returncode})")
        )
        sections = [
            "MICROSERV STORE | LIVE LOCAL KUBERNETES EVIDENCE (6 MICROSERVICES)",
            "Real command output rendered to video; no desktop capture.",
            time.strftime("UTC %Y-%m-%d %H:%M:%S", time.gmtime()),
            f"Context: {args.context} | scenario: {args.scenario} | users: {args.users} | load: {status}",
            "",
        ]
        sample = {
            "utc": sections[2],
            "load_status": status,
            "load_users": args.users,
            "scenario": args.scenario,
            "context": args.context,
        }
        for label, cmd in [
            ("HPA", ["get", "hpa"]),
            ("DEPLOYMENTS", ["get", "deployments"]),
            ("CPU AND MEMORY", ["top", "pods"]),
        ]:
            result = subprocess.run(base + cmd, capture_output=True, text=True, timeout=20)
            text = result.stdout or result.stderr
            sample[label] = text
            sections.extend([label, text.rstrip(), ""])
        snapshots.append(sample)
        temporary = output / "live-hpa.next"
        temporary.write_bytes("\n".join(sections).encode("utf-8"))
        temporary.replace(live)
        time.sleep(3)
    if load is not None:
        load.wait(timeout=30)
        if load.returncode:
            raise RuntimeError("Load failed; inspect recorded-load.log")
finally:
    if load is not None and load.poll() is None:
        load.terminate()
        load.wait()
    loadlog.close()
    Path(args.snapshot_output).write_text(json.dumps(snapshots, indent=2))

if shutil.which("ffmpeg"):
    subprocess.run(
        [
            sys.executable,
            "scripts/render-evidence.py",
            "--input",
            args.snapshot_output,
            "--output",
            args.video_output,
        ],
        check=True,
    )
    print(f"Recorded {args.video_output}: replay of real commands and concurrent {args.scenario} load")
else:
    print(f"Saved snapshots to {args.snapshot_output} (ffmpeg not installed, skipping mp4 render)")
