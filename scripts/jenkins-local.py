"""Authenticated local Jenkins validator. Never print local admin credentials."""
import argparse
import base64
import http.cookiejar
import json
import re
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from xml.sax.saxutils import escape as escape_xml

ROOT=Path(__file__).resolve().parents[1]
ENV=dict(line.split('=',1) for line in (ROOT/'.env.jenkins').read_text().splitlines() if '=' in line)
URL='http://127.0.0.1:8085'
OPENER=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
AUTH='Basic '+base64.b64encode(('admin:'+ENV['JENKINS_ADMIN_PASSWORD']).encode()).decode()
ARTIFACTS=ROOT/'artifacts'/'jenkins'
ARTIFACTS.mkdir(parents=True,exist_ok=True)

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
        body=(f'--{boundary}\r\nContent-Disposition: form-data; name="jenkinsfile"\r\n\r\n').encode()+path.read_bytes()+f'\r\n--{boundary}--\r\n'.encode()
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
    escape=escape_xml
    xml=f'''<flow-definition plugin="workflow-job"><description>Local validation using exact committed SCM mirrors. Service jobs publish to the authorized uyris Docker Hub namespace. Optional deploy targets only the configured kubeconfig.</description><keepDependencies>false</keepDependencies><properties/><definition class="org.jenkinsci.plugins.workflow.cps.CpsScmFlowDefinition" plugin="workflow-cps"><scm class="hudson.plugins.git.GitSCM" plugin="git"><configVersion>2</configVersion><userRemoteConfigs><hudson.plugins.git.UserRemoteConfig><url>{escape(repository)}</url></hudson.plugins.git.UserRemoteConfig></userRemoteConfigs><branches><hudson.plugins.git.BranchSpec><name>*/main</name></hudson.plugins.git.BranchSpec></branches><doGenerateSubmoduleConfigurations>false</doGenerateSubmoduleConfigurations><extensions/></scm><scriptPath>Jenkinsfile</scriptPath><lightweight>false</lightweight></definition><triggers/><disabled>false</disabled></flow-definition>'''.encode()
    if service!='root':
        parameters='''<properties><hudson.model.ParametersDefinitionProperty><parameterDefinitions>
          <hudson.model.StringParameterDefinition><name>DOCKERHUB_NAMESPACE</name><defaultValue>uyris</defaultValue></hudson.model.StringParameterDefinition>
          <hudson.model.BooleanParameterDefinition><name>DEPLOY</name><defaultValue>false</defaultValue></hudson.model.BooleanParameterDefinition>
        </parameterDefinitions></hudson.model.ParametersDefinitionProperty></properties>'''
        xml=xml.replace(b'<properties/>',parameters.encode())
    try:request('/job/'+name+'/config.xml',xml,'application/xml')
    except urllib.error.HTTPError as err:
        if err.code!=404:raise
        request('/createItem?name='+name,xml,'application/xml')
    print('Configured '+name)

def run(service,deploy=False):
    name='store-'+service
    suffix='/build' if service in ('root','negative') else '/buildWithParameters?'+urllib.parse.urlencode({'DOCKERHUB_NAMESPACE':'uyris','DEPLOY':str(deploy).lower()})
    request('/job/'+name+suffix,b'')
    print('Queued '+name)

def status(service):
    name='store-'+service
    result=json.loads(request('/job/'+name+'/lastBuild/api/json'))
    safe={key:result.get(key) for key in ['number','building','result','duration','url']}
    (ARTIFACTS/(name+'-status.json')).write_text(json.dumps(safe,indent=2))
    (ARTIFACTS/(name+'-console.txt')).write_bytes(request('/job/'+name+'/lastBuild/consoleText'))
    print(json.dumps(safe))

def negative():
    # This dedicated validation job creates no commits and changes no service repository.
    script="""pipeline {
      agent { label 'docker-kubectl' }
      stages {
        stage('Test') { steps { sh '''
          python3 -c 'assert 1 == 2'
        ''' } }
        stage('Build') { steps { echo 'MUST_NOT_EXECUTE' } }
        stage('Publish') { steps { echo 'MUST_NOT_EXECUTE' } }
        stage('Deploy') { steps { echo 'MUST_NOT_EXECUTE' } }
      }
    }"""
    config=('<flow-definition><description>Expected failure: assert 1 == 2; later stages must be skipped.</description>'
      '<definition class="org.jenkinsci.plugins.workflow.cps.CpsFlowDefinition"><script>'+escape_xml(script)+
      '</script><sandbox>true</sandbox></definition><disabled>false</disabled></flow-definition>').encode()
    try:request('/job/store-negative/config.xml',config,'application/xml')
    except urllib.error.HTTPError as err:
        if err.code!=404:raise
        request('/createItem?name=store-negative',config,'application/xml')
    run('negative')


def summary():
    results={}
    for service in ['root','account','auth','gateway','product','order','exchange','negative']:
        name='store-'+service
        build=json.loads(request('/job/'+name+'/lastBuild/api/json'))
        number=build['number']
        console=request(f'/job/{name}/{number}/consoleText').decode()
        (ARTIFACTS/f'{name}-{number}-console.txt').write_text(console,encoding='utf-8')
        entry={key:build.get(key) for key in ['number','building','result','duration','url']}
        commits=re.findall(r'Checking out Revision ([a-f0-9]{40})',console)
        digests=re.findall(r'([a-f0-9]{40}): digest: (sha256:[a-f0-9]{64})',console)
        entry.update(commit=commits[-1] if commits else None,
                     published_image_digest=digests[-1][1] if digests else None,
                     rollout_confirmed=f'deployment "{service}" successfully rolled out' in console)
        if service=='negative':
            entry['expected_failure_confirmed']=(build['result']=='FAILURE' and
                all(f'Stage "{stage}" skipped due to earlier failure' in console for stage in ['Build','Publish','Deploy'])
                and 'MUST_NOT_EXECUTE' not in console)
        results[service]=entry
    (ARTIFACTS/'summary.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    print(json.dumps(results,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['wait','lint','mirrors','job','run','status','negative','summary'])
    parser.add_argument('--service',default='root',choices=['root','account','auth','gateway','product','order','exchange','negative'])
    parser.add_argument('--deploy',action='store_true',help='Explicitly enable the configured deployment target')
    args=parser.parse_args()
    if args.action=='run':run(args.service,args.deploy)
    elif args.action in ('job','status'):globals()[args.action](args.service)
    else:globals()[args.action]()
