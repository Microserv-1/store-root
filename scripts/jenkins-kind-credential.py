"""Configure only the known local Kind cluster; never print/write kubeconfig secrets."""
import base64
import importlib.util
import json
from pathlib import Path
import subprocess
import urllib.parse

root=Path(__file__).resolve().parents[1]
context='kind-microserv-store'
controller='microserv-store-ci-jenkins-1'
info=json.loads(subprocess.check_output(['docker','inspect','microserv-store-control-plane']))[0]
if info['Config']['Labels'].get('io.x-k8s.kind.cluster')!='microserv-store':
    raise RuntimeError('Expected local Kind cluster not found')
config=json.loads(subprocess.check_output(['kubectl','--context',context,'config','view','--raw','--flatten','--minify','-o','json']))
if len(config['clusters'])!=1 or config['clusters'][0]['name']!=context:
    raise RuntimeError('Refusing a kubeconfig outside the local project context')
config['clusters'][0]['cluster']['server']='https://microserv-store-control-plane:6443'
networks=json.loads(subprocess.check_output(['docker','inspect',controller]))[0]['NetworkSettings']['Networks']
if 'kind' not in networks:
    subprocess.run(['docker','network','connect','kind',controller],check=True)
encoded=base64.b64encode(json.dumps(config).encode()).decode()
spec=importlib.util.spec_from_file_location('ci',root/'scripts'/'jenkins-local.py')
ci=importlib.util.module_from_spec(spec);spec.loader.exec_module(ci)
script='''
import com.cloudbees.plugins.credentials.SystemCredentialsProvider
import com.cloudbees.plugins.credentials.CredentialsScope
import com.cloudbees.plugins.credentials.domains.Domain
import com.cloudbees.plugins.credentials.SecretBytes
import org.jenkinsci.plugins.plaincredentials.impl.FileCredentialsImpl
def provider = SystemCredentialsProvider.getInstance()
def replacement = new FileCredentialsImpl(CredentialsScope.GLOBAL, 'store-kubeconfig',
    'LOCAL Kind microserv-store only; not AWS/EKS', 'kubeconfig.json', SecretBytes.fromBytes('CONFIG'.decodeBase64()))
def existing = provider.credentials.find { it.id == 'store-kubeconfig' }
if (existing) { provider.getStore().updateCredentials(Domain.global(), existing, replacement) }
else { provider.getStore().addCredentials(Domain.global(), replacement) }
provider.save()
println('Local Kind credential configured')
'''.replace('CONFIG',encoded)
response=ci.request('/scriptText',urllib.parse.urlencode({'script':script}).encode()).decode()
if 'Local Kind credential configured' not in response:
    raise RuntimeError('Provisioning failed; response omitted to protect secrets')
print('Configured local Kind credential; no AWS context used')
