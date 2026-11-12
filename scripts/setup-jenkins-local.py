"""Prepare isolated Jenkins storage and a random local password; print no secrets."""
import json
import argparse
from pathlib import Path
import secrets
import subprocess

parser=argparse.ArgumentParser()
parser.add_argument('--aws',action='store_true',help='Prepare separate AWS-agent controller storage/configuration, without starting it')
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
name='microserv-store-jenkins-aws-home' if args.aws else 'microserv-store-jenkins-home'
subprocess.run(['docker','volume','create',name],check=True,stdout=subprocess.DEVNULL)
info=json.loads(subprocess.check_output(['docker','volume','inspect',name]))[0]
path=root/('.env.jenkins.aws' if args.aws else '.env.jenkins')
if not path.exists():
    path.write_text(f"JENKINS_HOME_PATH={info['Mountpoint']}\nJENKINS_ADMIN_PASSWORD={secrets.token_hex(32)}\n")
    print('Generated '+path.name+'; random credentials are ignored by Git')
else:
    print('Preserved existing '+path.name)
