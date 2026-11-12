"""Configure actual GitHub SCM jobs in the authenticated LOCAL Jenkins.

Explicit --from-gh reuses this user's existing GitHub CLI credential in encrypted
local Jenkins storage. No token is printed, written into Git, or sent to GitHub
as a new resource. A separate fine-grained read credential can replace it later.
"""
import argparse
import base64
import importlib.util
import json
from pathlib import Path
import subprocess
import urllib.error
import urllib.parse
from xml.sax.saxutils import escape

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('jenkins',ROOT/'scripts/jenkins-local.py')
ci=importlib.util.module_from_spec(spec);spec.loader.exec_module(ci)
SERVICES=['root','account','auth','gateway','product','order','exchange']


def provision():
    result=subprocess.run(['gh','auth','token'],capture_output=True,text=True)
    if result.returncode:raise RuntimeError('Existing GitHub CLI credential unavailable')
    token=result.stdout.strip()
    user=subprocess.check_output(['gh','api','user','--jq','.login'],text=True).strip()
    if user.lower()!='uyris':raise ValueError('Unexpected GitHub account')
    script='''
import com.cloudbees.plugins.credentials.SystemCredentialsProvider
import com.cloudbees.plugins.credentials.CredentialsScope
import com.cloudbees.plugins.credentials.domains.Domain
import com.cloudbees.plugins.credentials.impl.UsernamePasswordCredentialsImpl
def provider = SystemCredentialsProvider.getInstance()
def replacement = new UsernamePasswordCredentialsImpl(CredentialsScope.GLOBAL, 'github-read',
 'GitHub checkout using existing local CLI identity; replace with dedicated read token for shared CI',
 'uyris', new String('TOKEN'.decodeBase64(), 'UTF-8'))
def existing = provider.credentials.find { it.id == 'github-read' }
if (existing) { provider.getStore().updateCredentials(Domain.global(), existing, replacement) }
else { provider.getStore().addCredentials(Domain.global(), replacement) }
provider.save()
println('GitHub checkout credential configured')
'''.replace('TOKEN',base64.b64encode(token.encode()).decode())
    response=ci.request('/scriptText',urllib.parse.urlencode({'script':script}).encode()).decode()
    if 'GitHub checkout credential configured' not in response:raise RuntimeError('Provisioning failed; response omitted to protect secrets')
    print('Configured authenticated GitHub SCM credential in local Jenkins')


def remove_mirror_redirects():
    for service in SERVICES:
        key='url.file://'+ci.ENV['JENKINS_HOME_PATH']+'/repos/store-'+service+'.git.insteadOf'
        prefix=['docker','exec','microserv-store-ci-jenkins-1','git','config','--global']
        existing=subprocess.run(prefix+['--get-all',key],capture_output=True,text=True)
        if existing.returncode==0:
            if existing.stdout.strip()!='https://github.com/Microserv-1/store-'+service+'.git':
                raise RuntimeError('Unexpected Git rewrite; refusing to alter unrelated configuration')
            subprocess.run(prefix+['--unset-all',key],check=True)
    print('Removed only project-owned mirror redirects from the controller Git configuration')


def job(service,eks=False):
    name='store-eks-release' if eks else 'github-store-'+service
    repository='https://github.com/Microserv-1/store-'+service+'.git'
    script_path='Jenkinsfile.eks' if eks else 'Jenkinsfile'
    if eks:
        parameters='''<hudson.model.BooleanParameterDefinition><name>DEPLOY_EKS</name><defaultValue>false</defaultValue></hudson.model.BooleanParameterDefinition>
        <hudson.model.StringParameterDefinition><name>KUBE_CONTEXT</name><defaultValue></defaultValue></hudson.model.StringParameterDefinition>'''
    elif service!='root':
        parameters='''<hudson.model.StringParameterDefinition><name>DOCKERHUB_NAMESPACE</name><defaultValue>uyris</defaultValue></hudson.model.StringParameterDefinition>
        <hudson.model.BooleanParameterDefinition><name>DEPLOY</name><defaultValue>false</defaultValue></hudson.model.BooleanParameterDefinition>'''
    else:parameters=''
    properties='<properties><hudson.model.ParametersDefinitionProperty><parameterDefinitions>'+parameters+'</parameterDefinitions></hudson.model.ParametersDefinitionProperty></properties>' if parameters else '<properties/>'
    xml=f'''<flow-definition><description>Actual GitHub SCM. Service jobs build/publish with DEPLOY=false for EKS; store-eks-release applies reviewed RDS CA overlays.</description>{properties}<definition class="org.jenkinsci.plugins.workflow.cps.CpsScmFlowDefinition"><scm class="hudson.plugins.git.GitSCM"><configVersion>2</configVersion><userRemoteConfigs><hudson.plugins.git.UserRemoteConfig><url>{escape(repository)}</url><credentialsId>github-read</credentialsId></hudson.plugins.git.UserRemoteConfig></userRemoteConfigs><branches><hudson.plugins.git.BranchSpec><name>*/main</name></hudson.plugins.git.BranchSpec></branches><extensions/></scm><scriptPath>{script_path}</scriptPath><lightweight>false</lightweight></definition><disabled>false</disabled></flow-definition>'''.encode()
    try:ci.request('/job/'+name+'/config.xml',xml,'application/xml')
    except urllib.error.HTTPError as error:
        if error.code!=404:raise
        ci.request('/createItem?name='+name,xml,'application/xml')
    print('Configured '+name+' from actual GitHub SCM')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--from-gh',action='store_true',help='Reuse the existing authenticated GitHub CLI credential in local encrypted Jenkins storage')
    args=parser.parse_args()
    if args.from_gh:provision()
    remove_mirror_redirects()
    for service in SERVICES:job(service)
    job('root',eks=True)
    (ROOT/'artifacts/jenkins/github-scm.json').write_text(json.dumps({'scm':'actual GitHub HTTPS, no local URL redirects',
        'services':SERVICES,'eks_job':'store-eks-release','default_deploy':False,
        'credential_note':'Uses existing local CLI identity when --from-gh is supplied; no GitHub commits or settings modified.'},indent=2)+'\n')
