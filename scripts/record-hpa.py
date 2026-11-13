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
parser.add_argument("--output-directory",default="artifacts")
parser.add_argument("--cooldown",type=int,default=0,help="Seconds observed after the load; no new load is generated")
parser.add_argument("--allow-eks-load",action="store_true",help="Explicit operator authorization required for this bounded cloud run")
args=parser.parse_args()
cloud=args.context=='store-eks' or not args.context.startswith(('kind-','minikube'))
if cloud and not args.allow_eks_load:
    parser.error("Cloud load requires prior cost approval and --allow-eks-load; nothing was executed")
if cloud and (not 1<=args.users<=8 or not 1<=args.duration<=120 or not 0<=args.cooldown<=360):
    parser.error("Bounded recording requires users 1..8, load duration 1..120s, cooldown 0..360s")
if cloud and args.output_directory=='artifacts':
    parser.error("Choose a separate --output-directory for cloud evidence")
ffmpeg=shutil.which("ffmpeg")
if not ffmpeg:parser.error("ffmpeg and Pillow are required")
if cloud:
    subprocess.run([sys.executable,"scripts/aws-cost-guard.py","--context",args.context],check=True)
output=Path(args.output_directory);output.mkdir(parents=True,exist_ok=True)
if (output/"recorded-hpa.json").exists():parser.error("Recording exists; choose a new output directory")
live=output/"live-hpa.txt"
live.write_text("Starting live Kubernetes evidence...",encoding="utf-8")
load=None
loadlog=(output/"recorded-load.log").open("w")
started=time.monotonic();snapshots=[];last_guard=started
deadline=started+args.duration+20+args.cooldown
base=["kubectl","--context",args.context,"-n","store"]
try:
    while time.monotonic() < deadline:
        elapsed=time.monotonic()-started
        if cloud and time.monotonic()-last_guard>=30:
            subprocess.run([sys.executable,"scripts/aws-cost-guard.py","--context",args.context],check=True)
            last_guard=time.monotonic()
            if time.monotonic()>=deadline:break
        if elapsed>=10 and load is None:
            load=subprocess.Popen([sys.executable,"scripts/load.py","--base-url",args.base_url,"--users",str(args.users),
                "--duration",str(args.duration),"--scenario","login","--output",str(output/("login-load.json" if cloud else "k8s-login-final.json"))],stdout=loadlog,stderr=loadlog)
        status="BASELINE" if load is None else ("RUNNING" if load.poll() is None else f"FINISHED (exit {load.returncode})")
        sections=["MICROSERV STORE | LIVE KUBERNETES EVIDENCE",
                  "Real command output rendered to video; no desktop capture.",
                  time.strftime("UTC %Y-%m-%d %H:%M:%S",time.gmtime()),
                  f"Context: {args.context} | login users: {args.users} | load: {status}",""]
        sample={"utc":sections[2],"load_status":status,"load_users":args.users,"context":args.context}
        for label,cmd in [("HPA",["get","hpa"]),("DEPLOYMENTS",["get","deployments"]),("CPU AND MEMORY",["top","pods","-l","app=account"])]:
            if time.monotonic()>=deadline:break
            result=subprocess.run(base+cmd,capture_output=True,text=True,timeout=20)
            text=result.stdout or result.stderr
            sample[label]=text
            sections.extend([label,text.rstrip(),""])
        if time.monotonic()>=deadline:break
        structured=subprocess.run(base+["get","hpa","-o","json"],capture_output=True,text=True,timeout=20,check=True)
        sample['hpa_status']=[{'name':h['metadata']['name'],'current':h.get('status',{}).get('currentReplicas'),
                              'desired':h.get('status',{}).get('desiredReplicas')}
                             for h in json.loads(structured.stdout)['items']]
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
subprocess.run([sys.executable,"scripts/render-evidence.py","--directory",str(output)],check=True)
print("Recorded "+str(output/"hpa-evidence.mp4")+": replay of real commands and concurrent login load; inspect snapshots before claiming HPA scaling")
