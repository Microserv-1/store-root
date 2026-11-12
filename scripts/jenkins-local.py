"""Authenticated local Jenkins validator. Never print local admin credentials."""
import argparse
import base64
import http.cookiejar
import json
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.sax.saxutils

ROOT=Path(__file__).resolve().parents[1]
ENV=dict(line.split('=',1) for line in (ROOT/'.env.jenkins').read_text().splitlines() if '=' in line)
URL='http://127.0.0.1:8085'
OPENER=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
AUTH='Basic '+base64.b64encode(('admin:'+ENV['JENKINS_ADMIN_PASSWORD']).encode()).decode()
ARTIFACTS=ROOT/'artifacts'/'jenkins'
ARTIFACTS.mkdir(exist_ok=True)

def request(path,data=None,content_type='application/x-www-form-urlencoded',crumb=True):
    headers={'Authorization':AUTH}
    if data is not None:
        headers['Content-Type']=content_type
        if crumb:
            token=json.loads(request('/crumbIssuer/api/json',crumb=False))
            headers[token['crumbRequestField']]=token['crumb']
    req=urllib.request.Request(URL+path,data=data,headers=headers)
    with OPENER.open(req,timeout=90) as response:return response.read()

def wait():
    for _ in range(120):
        try:
            request('/api/json')
            print('Authenticated Jenkins is ready')
            return
        except (OSError,urllib.error.HTTPError):time.sleep(2)
    raise RuntimeError('Jenkins did not become ready')

def lint():
    results={}
    for service in ['root','account','auth','gateway','product','order','exchange']:
        path=ROOT/'Jenkinsfile' if service=='root' else ROOT/'api'/service/'Jenkinsfile'
        boundary='StorePipelineValidationBoundary'
        body=(f'--{boundary}\r\nContent-Disposition: form-data; name="jenkinsfile"; filename="Jenkinsfile"\r\nContent-Type: text/plain\r\n\r\n').encode()+path.read_bytes()+f'\r\n--{boundary}--\r\n'.encode()
        result=request('/pipeline-model-converter/validate',body,'multipart/form-data; boundary='+boundary).decode()
        results[service]=result.strip()
        print(service+': '+result.strip())
    (ARTIFACTS/'lint.json').write_text(json.dumps(results,indent=2))
    if not all('successfully validated' in value.lower() for value in results.values()):raise RuntimeError('Jenkins linter rejected a pipeline')

def mirrors():
    local=ARTIFACTS/'scm'
    local.mkdir(exist_ok=True)
    for service in ['root','account','auth','gateway','product','order','exchange']:
        source=ROOT if service=='root' else ROOT/'api'/service
        destination=local/('store-'+service+'.git')
        if not destination.exists():subprocess.run(['git','clone','--bare','--no-hardlinks',str(source),str(destination)],check=True)
        else:subprocess.run(['git','-C',str(destination),'fetch',str(source),'main:main'],check=True)
    subprocess.run(['docker','cp',str(local)+ '/.','microserv-store-ci-jenkins-1:'+ENV['JENKINS_HOME_PATH']+'/repos'],check=True)
    for service in ['root','account','auth','gateway','product','order','exchange']:
        destination='file://'+ENV['JENKINS_HOME_PATH']+'/repos/store-'+service+'.git'
        subprocess.run(['docker','exec','microserv-store-ci-jenkins-1','git','config','--global','--replace-all',
                        'url.'+destination+'.insteadOf','https://github.com/Microserv-1/store-'+service+'.git'],check=True)
    subprocess.run(['docker','exec','microserv-store-ci-jenkins-1','git','config','--global','protocol.file.allow','always'],check=True)
    print('Prepared local SCM mirrors; no GitHub credential exported into Jenkins')

def job(service):
    name='store-'+service
    repository='file://'+ENV['JENKINS_HOME_PATH']+'/repos/store-'+service+'.git'
    escape=xml.sax.saxutils.escape
    xml=f'''<flow-definition plugin="workflow-job"><description>Local validation using an exact committed SCM mirror. Does not prove Docker Hub publication.</description><keepDependencies>false</keepDependencies><properties/><definition class="org.jenkinsci.plugins.workflow.cps.CpsScmFlowDefinition" plugin="workflow-cps"><scm class="hudson.plugins.git.GitSCM" plugin="git"><configVersion>2</configVersion><userRemoteConfigs><hudson.plugins.git.UserRemoteConfig><url>{escape(repository)}</url></hudson.plugins.git.UserRemoteConfig></userRemoteConfigs><branches><hudson.plugins.git.BranchSpec><name>*/main</name></hudson.plugins.git.BranchSpec></branches><doGenerateSubmoduleConfigurations>false</doGenerateSubmoduleConfigurations><extensions/></scm><scriptPath>Jenkinsfile</scriptPath><lightweight>false</lightweight></definition><triggers/><disabled>false</disabled></flow-definition>'''.encode()
    try:request('/job/'+name+'/config.xml',xml,'application/xml')
    except urllib.error.HTTPError as err:
        if err.code!=404:raise
        request('/createItem?name='+name,xml,'application/xml')
    print('Configured '+name)

def run(service):
    name='store-'+service
    suffix='/build' if service=='root' else '/buildWithParameters?'+urllib.parse.urlencode({'DOCKERHUB_NAMESPACE':'local-validation','DEPLOY':'false'})
    request('/job/'+name+suffix,b'')
    print('Queued '+name)

def status(service):
    name='store-'+service
    result=json.loads(request('/job/'+name+'/lastBuild/api/json'))
    safe={key:result.get(key) for key in ['number','building','result','duration','url']}
    (ARTIFACTS/(name+'-status.json')).write_text(json.dumps(safe,indent=2))
    (ARTIFACTS/(name+'-console.txt')).write_bytes(request('/job/'+name+'/lastBuild/consoleText'))
    print(json.dumps(safe))

parser=argparse.ArgumentParser()
parser.add_argument('action',choices=['wait','lint','mirrors','job','run','status'])
parser.add_argument('--service',default='root',choices=['root','account','auth','gateway','product','order','exchange'])
args=parser.parse_args()
if args.action in ('job','run','status'):globals()[args.action](args.service)
else:globals()[args.action]()
