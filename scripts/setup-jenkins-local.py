"""Prepare isolated Jenkins storage and a random local password; print no secrets."""
import json
from pathlib import Path
import secrets
import subprocess

root=Path(__file__).resolve().parents[1]
name='microserv-store-jenkins-home'
subprocess.run(['docker','volume','create',name],check=True,stdout=subprocess.DEVNULL)
info=json.loads(subprocess.check_output(['docker','volume','inspect',name]))[0]
path=root/'.env.jenkins'
if not path.exists():
    path.write_text(f"JENKINS_HOME_PATH={info['Mountpoint']}\nJENKINS_ADMIN_PASSWORD={secrets.token_hex(32)}\n")
    print('Generated .env.jenkins; random credentials are ignored by Git')
else:
    print('Preserved existing .env.jenkins')
