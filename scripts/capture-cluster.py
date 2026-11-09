"""Capture non-secret cluster evidence at intervals while an independent load test runs."""
import argparse
import json
from pathlib import Path
import subprocess
import time
parser=argparse.ArgumentParser()
parser.add_argument("--context",required=True)
parser.add_argument("--duration",type=int,default=180)
parser.add_argument("--output",default="artifacts/cluster.json")
args=parser.parse_args()
snapshots=[]
stop=time.monotonic()+args.duration
while True:
    sample={"utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())}
    for label,command in [("pods",["get","pods","-o","wide"]),("hpa",["get","hpa"]),("resources",["top","pods"])]:
        result=subprocess.run(["kubectl","--context",args.context,"-n","store"]+command,capture_output=True,text=True)
        sample[label]=result.stdout or result.stderr
    snapshots.append(sample)
    print(sample["utc"],sample["hpa"],flush=True)
    if time.monotonic()>=stop:break
    time.sleep(min(10,max(0,stop-time.monotonic())))
path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(snapshots,indent=2))
