"""Apply/restore only application resources. Infrastructure and secrets are operator-owned."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def run(context,*args,document=None):
    result=subprocess.run(['kubectl','--context',context,*args],input=json.dumps(document) if document else None,
                          capture_output=True,text=True)
    if result.returncode:raise RuntimeError(result.stderr.strip())
    return result.stdout


def clean(resource):
    result=copy.deepcopy(resource);result.pop('status',None)
    for key in ['uid','resourceVersion','generation','creationTimestamp','managedFields','selfLink']:
        result['metadata'].pop(key,None)
    result['metadata'].get('annotations',{}).pop('kubectl.kubernetes.io/last-applied-configuration',None)
    return result


def validate_resources(resources,allowed):
    for resource in resources:
        key=(resource['kind'],resource['metadata']['name'])
        if key not in allowed or resource['metadata'].get('namespace')!='store':
            raise ValueError('Resource is outside the reviewed application release')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['apply','rollback'])
    parser.add_argument('--directory',default='artifacts/eks')
    parser.add_argument('--context',required=True)
    parser.add_argument('--config',default='.env.eks.json')
    parser.add_argument('--from-file',help='Previously saved application snapshot for rollback')
    parser.add_argument('--local-validation',action='store_true',help='Explicitly allow known Kind context for local overlay/rollback QA')
    args=parser.parse_args();directory=ROOT/args.directory
    release=json.loads((directory/'applications.json').read_text())
    metadata=json.loads((directory/'release-metadata.json').read_text())
    allowed={(r['kind'],r['metadata']['name']) for r in release['items']}
    if args.local_validation:
        if args.context!='kind-microserv-store':raise ValueError('Local mode is restricted to the known Kind context')
    else:
        if metadata['example_only']:raise ValueError('Refusing to deploy an example-only release to AWS')
        spec=importlib.util.spec_from_file_location('preflight',ROOT/'scripts/eks-preflight.py')
        preflight=importlib.util.module_from_spec(spec);spec.loader.exec_module(preflight)
        config=preflight.prepare.load_config(args.config)
        if config!=metadata['config']:raise ValueError('Config differs from reviewed release')
        if args.action=='rollback':preflight.target_only(config,args.context)
        else:preflight.cloud(config,args.context)
    validate_resources(release['items'],allowed)
    if args.action=='apply':
        previous=[];missing=[]
        for resource in release['items']:
            raw=run(args.context,'-n','store','get',resource['kind'],resource['metadata']['name'],'--ignore-not-found','-o','json')
            if raw.strip():previous.append(clean(json.loads(raw)))
            else:missing.append({'kind':resource['kind'],'name':resource['metadata']['name']})
        (directory/'rollback.json').write_text(json.dumps({'apiVersion':'v1','kind':'List','items':previous},indent=2)+'\n')
        (directory/'new-resources.json').write_text(json.dumps(missing,indent=2)+'\n')
        target=release
    else:
        if not args.from_file:parser.error('--from-file is required for rollback')
        target=json.loads(Path(args.from_file).read_text())
        validate_resources(target['items'],allowed)
        preceding={r['metadata']['name'] for r in target['items'] if r['kind']=='Deployment'}
        if preceding!={'account','auth','gateway','product','order','exchange'}:
            raise ValueError('No complete preceding six-service release exists; first deployment requires operator recovery')
    print(run(args.context,'apply','--dry-run=server','-f','-',document=target))
    print(run(args.context,'apply','-f','-',document=target))
    for resource in target['items']:
        if resource['kind']=='Deployment':
            print(run(args.context,'-n','store','rollout','status','deployment/'+resource['metadata']['name'],'--timeout=300s'))
    print('PASS: '+args.action+' completed for reviewed application resources; bootstrap/dependencies unchanged')
    if args.action=='rollback':
        print('Resources absent in the previous release are retained; review new-resources.json with the operator. Database migrations are not rolled back.')


if __name__=='__main__':main()
