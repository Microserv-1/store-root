"""Offline release checks, optional local server dry-run, optional READ-ONLY AWS checks.

This script never provisions AWS resources and never applies the rendered release.
"""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import time
import yaml

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('prepare',ROOT/'scripts/prepare-eks.py')
prepare=importlib.util.module_from_spec(spec);spec.loader.exec_module(prepare)


def command(args):
    result=subprocess.run(args,capture_output=True,text=True)
    if result.returncode:raise RuntimeError('Command failed (credentials/error details omitted): '+' '.join(args[:3]))
    return result.stdout


def offline(directory):
    release=json.loads((directory/'release.json').read_text());bootstrap=json.loads((directory/'bootstrap.json').read_text())
    items=release['items'];metadata=json.loads((directory/'release-metadata.json').read_text())
    assert not any(r['kind']=='Secret' for r in items+bootstrap['items']), 'Rendered artifacts must never contain Secrets'
    deployments={r['metadata']['name']:r for r in items if r['kind']=='Deployment'}
    assert set(prepare.SERVICES).issubset(deployments)
    for name in prepare.SERVICES:
        container=deployments[name]['spec']['template']['spec']['containers'][0]
        assert container['image']==metadata['images'][name]['image'] and '@sha256:' in container['image']
        assert container['resources']['requests'] and container['readinessProbe'] and container['startupProbe']
        if name in ['account','product','order']:
            assert any(v['name']=='rds-ca' for v in container['volumeMounts'])
    assert not {'postgres','product-db','order-db'}.intersection(deployments), 'Cloud must use the isolated RDS databases'
    assert all(r['spec'].get('type','ClusterIP')=='ClusterIP' for r in items if r['kind']=='Service')
    ingress=next(r for r in items if r['kind']=='Ingress')
    annotations=ingress['metadata']['annotations']
    assert annotations['alb.ingress.kubernetes.io/ssl-redirect']=='443'
    assert json.loads(annotations['alb.ingress.kubernetes.io/listen-ports'])==[{'HTTP':80},{'HTTPS':443}]
    assert ingress['spec']['rules'][0]['http']['paths'][0]['backend']['service']['name']=='gateway'
    rabbit=next(r for r in items if r['kind']=='StatefulSet' and r['metadata']['name']=='rabbitmq')
    assert rabbit['spec']['volumeClaimTemplates'][0]['spec']['storageClassName']=='store-gp3'
    storage=next(r for r in items if r['kind']=='StorageClass')
    assert storage['reclaimPolicy']=='Retain' and storage['parameters']['encrypted']=='true'
    roles=[r for r in items if r['kind']=='Role' and r['metadata']['name']=='store-deployer']
    assert len(roles)==1 and not any('secrets' in rule['resources'] or '*' in rule['verbs'] for rule in roles[0]['rules'])
    assert bootstrap['items'][1]['metadata']['namespace']=='store-bootstrap'
    return {'example_only':metadata['example_only'],'resource_count':len(items),'offline_checks':'PASS'}


def local_dry_run(directory,context):
    if context!='kind-microserv-store':raise ValueError('Local validation is restricted to the known project Kind context')
    # Namespace creates in a dry-run are not persisted. Validate bootstrap object
    # schemas in the existing store namespace, without creating a cloud namespace.
    for filename in ['release.json','bootstrap.json']:
        document=json.loads((directory/filename).read_text())
        for resource in document['items']:
            if resource.get('metadata',{}).get('namespace')=='store-bootstrap':resource['metadata']['namespace']='store'
        result=subprocess.run(['kubectl','--context',context,'apply','--dry-run=server','-f','-'],
            input=json.dumps(document),capture_output=True,text=True)
        if result.returncode:raise RuntimeError('Local server dry-run failed: '+result.stderr)
    return 'PASS (Kind API schema only; AWS controllers/storage were not executed)'


def cloud(config,context=None):
    region=config['region']
    def aws(*args):return json.loads(command(['aws',*args,'--region',region,'--output','json']))
    identity=aws('sts','get-caller-identity')
    if identity['Account']!=config['account_id']:raise ValueError('AWS identity account differs from release configuration')
    versions=aws('eks','describe-cluster-versions','--cluster-versions',config['kubernetes_version'])['clusterVersions']
    if not versions or versions[0].get('versionStatus',versions[0].get('status','')).upper()!='STANDARD_SUPPORT':
        raise ValueError('Pinned Kubernetes version is not in standard support in the target region')
    certificate=aws('acm','describe-certificate','--certificate-arn',config['certificate_arn'])['Certificate']
    if certificate['Status']!='ISSUED':raise ValueError('ACM certificate must be ISSUED')
    names=certificate.get('SubjectAlternativeNames',[])
    def matches(name):return name==config['domain'] or (name.startswith('*.') and config['domain'].split('.',1)[1]==name[2:])
    if not any(matches(name) for name in names):raise ValueError('ACM certificate does not cover the application domain')
    subnets=aws('ec2','describe-subnets','--subnet-ids',*config['public_subnets'])['Subnets']
    if len({s['VpcId'] for s in subnets})!=1 or len({s['AvailabilityZone'] for s in subnets})<2:
        raise ValueError('Load balancer subnets must share the EKS VPC and span two AZs')
    result={'account':identity['Account'],'caller_arn':identity['Arn'],'kubernetes_version':config['kubernetes_version'],
            'certificate_status':certificate['Status'],'subnet_vpc':subnets[0]['VpcId'],
            'note':'Read-only AWS checks; this does not prove provisioning or workload health'}
    if context:
        cluster=aws('eks','describe-cluster','--name',config['cluster'])['cluster']
        if cluster['status']!='ACTIVE' or cluster['version']!=config['kubernetes_version']:
            raise ValueError('Target cluster is not ACTIVE with the pinned version')
        if cluster['resourcesVpcConfig']['vpcId']!=subnets[0]['VpcId']:
            raise ValueError('ALB subnets are outside the EKS VPC')
        kube=json.loads(command(['kubectl','--context',context,'config','view','--minify','-o','json']))
        if kube['clusters'][0]['cluster']['server']!=cluster['endpoint']:
            raise ValueError('Kubeconfig points at another cluster endpoint')
        controller=json.loads(command(['kubectl','--context',context,'-n','kube-system','get','deployment','aws-load-balancer-controller','-o','json']))
        if controller.get('status',{}).get('availableReplicas',0)<1:raise ValueError('AWS Load Balancer Controller is not ready')
        command(['kubectl','--context',context,'get','csidriver','ebs.csi.aws.com'])
        metrics=json.loads(command(['kubectl','--context',context,'get','apiservice','v1beta1.metrics.k8s.io','-o','json']))
        if not any(c['type']=='Available' and c['status']=='True' for c in metrics.get('status',{}).get('conditions',[])):
            raise ValueError('Metrics API is unavailable')
        nodes=json.loads(command(['kubectl','--context',context,'get','nodes','-o','json']))['items']
        if len(nodes)<config['nodes'] or any(not any(c['type']=='Ready' and c['status']=='True' for c in n['status']['conditions']) for n in nodes):
            raise ValueError('Expected ready worker capacity not found')
        result.update(cluster_arn=cluster['arn'],context=context,ready_nodes=len(nodes),endpoint_matches=True)
    return result


def target_only(config,context):
    # Recovery must still confirm identity/target, but must not depend on healthy
    # metrics, ingress controller, or an unexpired public certificate.
    region=config['region']
    identity=json.loads(command(['aws','sts','get-caller-identity','--region',region,'--output','json']))
    if identity['Account']!=config['account_id']:raise ValueError('Unexpected AWS account')
    cluster=json.loads(command(['aws','eks','describe-cluster','--name',config['cluster'],'--region',region,'--output','json']))['cluster']
    kube=json.loads(command(['kubectl','--context',context,'config','view','--minify','-o','json']))
    if cluster['status']!='ACTIVE' or kube['clusters'][0]['cluster']['server']!=cluster['endpoint']:
        raise ValueError('Recovery context does not match the ACTIVE target EKS cluster')
    return {'account':identity['Account'],'cluster':cluster['arn'],'endpoint_matches':True}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--directory',default='artifacts/eks')
    parser.add_argument('--local-context')
    parser.add_argument('--cloud',action='store_true')
    parser.add_argument('--cluster-context',help='With --cloud, also check the existing EKS cluster and controllers')
    parser.add_argument('--config',default='.env.eks.json')
    args=parser.parse_args();directory=ROOT/args.directory
    result={'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),**offline(directory)}
    if args.local_context:result['local_server_dry_run']=local_dry_run(directory,args.local_context)
    if args.cloud:
        config=prepare.load_config(args.config)
        if result['example_only']:raise ValueError('Refusing AWS validation of an example-only release')
        metadata=json.loads((directory/'release-metadata.json').read_text())
        if config!=metadata['config']:raise ValueError('Config differs from rendered release; render again')
        result['aws']=cloud(config,args.cluster_context)
    (directory/'preflight.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
