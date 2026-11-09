"""Record live kubectl output and a real concurrent load run, without desktop capture."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

parser=argparse.ArgumentParser()
parser.add_argument("--context",default="kind-microserv-store")
parser.add_argument("--base-url",default="http://127.0.0.1:8082")
parser.add_argument("--duration",type=int,default=90)
parser.add_argument("--users",type=int,default=4)
args=parser.parse_args()
ffmpeg=shutil.which("ffmpeg")
if not ffmpeg:parser.error("ffmpeg and Pillow are required")
output=Path("artifacts");output.mkdir(exist_ok=True)
live=output/"live-hpa.txt"
live.write_text("Starting live Kubernetes evidence...",encoding="utf-8")
load=None
loadlog=(output/"recorded-load.log").open("w")
started=time.monotonic();snapshots=[]
base=["kubectl","--context",args.context,"-n","store"]
try:
    while time.monotonic()-started < args.duration+20:
        elapsed=time.monotonic()-started
        if elapsed>=10 and load is None:
            load=subprocess.Popen([sys.executable,"scripts/load.py","--base-url",args.base_url,"--users",str(args.users),
                "--duration",str(args.duration),"--scenario","login","--output","artifacts/k8s-login-final.json"],stdout=loadlog,stderr=loadlog)
        status="BASELINE" if load is None else ("RUNNING" if load.poll() is None else f"FINISHED (exit {load.returncode})")
        sections=["MICROSERV STORE | LIVE LOCAL KUBERNETES EVIDENCE",
                  "Real command output rendered to video; no desktop capture.",
                  time.strftime("UTC %Y-%m-%d %H:%M:%S",time.gmtime()),
                  f"Context: {args.context} | login users: {args.users} | load: {status}",""]
        sample={"utc":sections[2],"load_status":status,"load_users":args.users,"context":args.context}
        for label,cmd in [("HPA",["get","hpa"]),("DEPLOYMENTS",["get","deployments"]),("CPU AND MEMORY",["top","pods","-l","app=account"])]:
            result=subprocess.run(base+cmd,capture_output=True,text=True,timeout=20)
            text=result.stdout or result.stderr
            sample[label]=text
            sections.extend([label,text.rstrip(),""])
        snapshots.append(sample)
        # Atomic replacement prevents ffmpeg reading partially written lines.
        temporary=output/"live-hpa.next"
        temporary.write_bytes("\n".join(sections).encode("utf-8"))
        temporary.replace(live)
        time.sleep(3)
    if load is not None:
        load.wait(timeout=30)
        if load.returncode:raise RuntimeError("Load failed; inspect recorded-load.log")
finally:
    if load is not None and load.poll() is None:load.terminate();load.wait()
    loadlog.close()
    (output/"recorded-hpa.json").write_text(json.dumps(snapshots,indent=2))
subprocess.run([sys.executable,"scripts/render-evidence.py"],check=True)
print("Recorded artifacts/hpa-evidence.mp4: replay of real commands and concurrent login load")
