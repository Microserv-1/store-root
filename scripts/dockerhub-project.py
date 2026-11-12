"""Manage the explicitly authorized public project repositories; never log credentials."""
import argparse
import base64
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
NAMESPACE='uyris'
SERVICES=['account','auth','gateway','product','order','exchange']

def credential():
    config=json.loads((Path.home()/'.docker'/'config.json').read_text())
    helper=shutil.which('docker-credential-'+config.get('credsStore','desktop')+'.exe')
    result=subprocess.run([helper,'get'],input='https://index.docker.io/v1/\n',capture_output=True,text=True)
    if result.returncode:raise RuntimeError('Docker Hub credential unavailable in the local helper')
    data=json.loads(result.stdout)
    if data['Username']!=NAMESPACE:raise RuntimeError('Unexpected Docker account; refusing to change namespace')
    return data['Username'],data['Secret']

def create():
    user,secret=credential()
    def api(path,data=None,token=None):
        headers={'Content-Type':'application/json'}
        if token:headers['Authorization']='Bearer '+token
        req=urllib.request.Request('https://hub.docker.com'+path,data=json.dumps(data).encode() if data is not None else None,headers=headers)
        with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)
    auth=api('/v2/auth/token',{'identifier':user,'secret':secret})
    token=auth['access_token']
    results=[]
    for service in SERVICES:
        name='store-'+service
        path=f'/v2/namespaces/{NAMESPACE}/repositories/{name}'
        try:
            repository=api(path,token=token)
        except urllib.error.HTTPError as err:
            if err.code!=404:raise
            repository=api(f'/v2/namespaces/{NAMESPACE}/repositories',{'name':name,'namespace':NAMESPACE,
                'is_private':False,'registry':'docker.io','description':'Microserv Store academic project — '+service},token)
        if repository.get('is_private') is not False:
            raise RuntimeError('Existing private repository needs explicit review: '+name)
        results.append({'name':NAMESPACE+'/'+name,'public':True,'url':'https://hub.docker.com/r/'+NAMESPACE+'/'+name})
        print('Ready public repository: '+NAMESPACE+'/'+name)
    target=ROOT/'artifacts'/'jenkins';target.mkdir(exist_ok=True)
    (target/'dockerhub-repositories.json').write_text(json.dumps(results,indent=2))

def jenkins_credential():
    user,secret=credential()
    spec=importlib.util.spec_from_file_location('store_jenkins',ROOT/'scripts'/'jenkins-local.py')
    jenkins=importlib.util.module_from_spec(spec);spec.loader.exec_module(jenkins)
    encoded=base64.b64encode(secret.encode()).decode()
    script='''
import com.cloudbees.plugins.credentials.SystemCredentialsProvider
import com.cloudbees.plugins.credentials.CredentialsScope
import com.cloudbees.plugins.credentials.domains.Domain
import com.cloudbees.plugins.credentials.impl.UsernamePasswordCredentialsImpl
def provider = SystemCredentialsProvider.getInstance()
def replacement = new UsernamePasswordCredentialsImpl(CredentialsScope.GLOBAL, 'dockerhub',
    'Authorized uyris project publication', 'uyris', new String('TOKEN'.decodeBase64(), 'UTF-8'))
def existing = provider.credentials.find { it.id == 'dockerhub' }
if (existing) { provider.getStore().updateCredentials(Domain.global(), existing, replacement) }
else { provider.getStore().addCredentials(Domain.global(), replacement) }
provider.save()
println('Docker Hub project credential configured')
'''.replace('TOKEN',encoded)
    response=jenkins.request('/scriptText',urllib.parse.urlencode({'script':script}).encode()).decode()
    if 'Docker Hub project credential configured' not in response:raise RuntimeError('Credential provisioning failed; response omitted to protect secrets')
    print('Docker Hub credential configured in authenticated local Jenkins')

parser=argparse.ArgumentParser()
parser.add_argument('action',choices=['create','jenkins-credential'])
args=parser.parse_args()
if args.action=='create':create()
else:jenkins_credential()
