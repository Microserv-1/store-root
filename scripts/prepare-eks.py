"""Render a six-service AWS release without provisioning or writing credentials.

Requires requirements-ops.txt. Example rendering is for offline validation only.
All B manifests are read, never edited. Images are locked by published digest.
"""
import argparse
import json
import ipaddress
from pathlib import Path
import re
import subprocess
import urllib.request
import yaml

ROOT=Path(__file__).resolve().parents[1]
SERVICES=['account','auth','gateway','product','exchange','order']


def load_config(path,example=False,cluster_only=False):
    config=json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,39}',config['cluster']):raise ValueError('Invalid cluster name')
    if not re.fullmatch(r'[a-z]{2}-[a-z]+-\d',config['region']):raise ValueError('Invalid AWS region')
    if not re.fullmatch(r'\d{12}',config['account_id']):raise ValueError('Invalid account ID')
    if not example and config['account_id']=='000000000000':raise ValueError('Replace the example AWS account ID')
    if config['kubernetes_version']!='1.35':raise ValueError('Revalidate manifests and kubectl before changing pinned Kubernetes 1.35')
    if config['node_instance_type'] not in ['t3.large','t3.xlarge'] or not 2<=config['nodes']<=4:
        raise ValueError('Reviewed worker bounds are 2..4 t3.large/t3.xlarge nodes')
    if config['rds_instance_class'] not in ['db.t4g.small','db.t4g.medium']:raise ValueError('Unreviewed database instance class')
    if len(config['availability_zones'])!=2 or any(not z.startswith(config['region']) for z in config['availability_zones']):
        raise ValueError('Choose two availability zones in the configured region')
    if not config['admin_cidrs']:raise ValueError('Explicit operator CIDR is required')
    for cidr in config['admin_cidrs']:
        network=ipaddress.ip_network(cidr,strict=True)
        if not example and (not network.network_address.is_global or network.prefixlen<24):
            raise ValueError('Use narrow real public operator CIDRs, never a documentation CIDR or 0.0.0.0/0')
    if cluster_only:return config
    if not re.fullmatch(r'(?=.{1,253}$)[a-z0-9]+(?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,}',config['domain']):raise ValueError('Invalid domain')
    certificate=f"arn:aws:acm:{config['region']}:{config['account_id']}:certificate/"
    if not re.fullmatch(re.escape(certificate)+r'[a-f0-9-]{36}',config['certificate_arn']):raise ValueError('Certificate region/account/ID mismatch')
    if len(config['public_subnets'])<2 or len(set(config['public_subnets']))!=len(config['public_subnets']):
        raise ValueError('Two different public subnets are required')
    if any(not re.fullmatch(r'subnet-[a-f0-9]{8,17}',s) for s in config['public_subnets']):raise ValueError('Invalid subnet ID')
    if not example and (config['account_id']=='000000000000' or config['domain'].endswith('example.com') or
                        any(s.startswith('subnet-0000') for s in config['public_subnets'])):
        raise ValueError('Replace example account, domain, certificate and subnets before preparing a real release')
    return config


def lock_images():
    result={}
    for name in SERVICES:
        sha=subprocess.check_output(['git','-C',str(ROOT/'api'/name),'rev-parse','HEAD'],text=True).strip()
        if subprocess.check_output(['git','-C',str(ROOT/'api'/name),'status','--porcelain'],text=True).strip():
            raise ValueError('Refusing to identify dirty source by HEAD: '+name)
        repository='uyris/store-'+name
        with urllib.request.urlopen(f'https://hub.docker.com/v2/repositories/{repository}/tags/{sha}',timeout=30) as response:
            tag=json.load(response)
        digest=tag.get('digest')
        if not digest or not re.fullmatch(r'sha256:[a-f0-9]{64}',digest):raise ValueError('Registry digest missing: '+name)
        result[name]={'commit':sha,'image':repository+':'+sha+'@'+digest}
    for name in ['redis','rabbitmq']:
        source='redis:7-alpine' if name=='redis' else 'rabbitmq:4-alpine'
        info=json.loads(subprocess.check_output(['docker','image','inspect',source]))[0]
        result[name]={'image':next(d for d in info['RepoDigests'] if d.startswith(name+'@'))}
    target=ROOT/'infra/aws/images.lock.json'
    target.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('Locked six published images and two installed dependencies; no registry writes')


def metadata(name,namespace='store'):return {'name':name,'namespace':namespace}
def env(name,key):return {'name':name,'valueFrom':{'secretKeyRef':{'name':'store-secrets','key':key}}}


def dependencies(lock,storage_class='store-gp3'):
    items=[{'apiVersion':'storage.k8s.io/v1','kind':'StorageClass','metadata':{'name':storage_class},
            'provisioner':'ebs.csi.aws.com','parameters':{'type':'gp3','encrypted':'true'},
            'volumeBindingMode':'WaitForFirstConsumer','allowVolumeExpansion':True,'reclaimPolicy':'Retain'}]
    for name,port in [('redis',6379),('rabbitmq',5672)]:
        items.append({'apiVersion':'v1','kind':'Service','metadata':metadata(name),
                      'spec':{'type':'ClusterIP','selector':{'app':name},'ports':[{'port':port,'targetPort':port}]}})
    items.append({'apiVersion':'v1','kind':'Service','metadata':metadata('rabbitmq-headless'),
                  'spec':{'clusterIP':'None','selector':{'app':'rabbitmq'},'ports':[{'port':5672,'targetPort':5672}]}})
    redis={'name':'redis','image':lock['redis']['image'],'ports':[{'containerPort':6379}],
           'command':['sh','-ec','exec redis-server --requirepass "$REDIS_PASSWORD" --maxmemory 128mb --maxmemory-policy allkeys-lru --save "" --appendonly no'],
           'env':[env('REDIS_PASSWORD','REDIS_PASSWORD')],
           'resources':{'requests':{'cpu':'50m','memory':'64Mi'},'limits':{'cpu':'500m','memory':'256Mi'}},
           'securityContext':{'runAsUser':999,'runAsGroup':1000,'runAsNonRoot':True,'allowPrivilegeEscalation':False,'capabilities':{'drop':['ALL']}},
           'readinessProbe':{'exec':{'command':['sh','-ec','REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli ping | grep -qx PONG']},'periodSeconds':5},
           'livenessProbe':{'tcpSocket':{'port':6379},'periodSeconds':10}}
    items.append({'apiVersion':'apps/v1','kind':'Deployment','metadata':metadata('redis'),
                  'spec':{'replicas':1,'strategy':{'type':'Recreate'},'selector':{'matchLabels':{'app':'redis'}},
                          'template':{'metadata':{'labels':{'app':'redis'}},'spec':{'automountServiceAccountToken':False,'containers':[redis]}}}})
    rabbit={'name':'rabbitmq','image':lock['rabbitmq']['image'],'ports':[{'containerPort':5672}],
            'env':[{'name':'RABBITMQ_DEFAULT_USER','value':'store'},env('RABBITMQ_DEFAULT_PASS','RABBITMQ_PASSWORD'),
                   {'name':'RABBITMQ_SERVER_ADDITIONAL_ERL_ARGS','value':'+S 2:2'}],
            'resources':{'requests':{'cpu':'200m','memory':'256Mi'},'limits':{'cpu':'1','memory':'768Mi'}},
            'securityContext':{'runAsUser':100,'runAsGroup':101,'runAsNonRoot':True,'allowPrivilegeEscalation':False,'capabilities':{'drop':['ALL']}},
            'volumeMounts':[{'name':'data','mountPath':'/var/lib/rabbitmq'}],
            'startupProbe':{'tcpSocket':{'port':5672},'periodSeconds':3,'failureThreshold':60},
            'readinessProbe':{'tcpSocket':{'port':5672},'periodSeconds':5},
            'livenessProbe':{'tcpSocket':{'port':5672},'periodSeconds':15,'failureThreshold':6}}
    items.append({'apiVersion':'apps/v1','kind':'StatefulSet','metadata':metadata('rabbitmq'),
                  'spec':{'serviceName':'rabbitmq-headless','replicas':1,'selector':{'matchLabels':{'app':'rabbitmq'}},
                    'persistentVolumeClaimRetentionPolicy':{'whenDeleted':'Retain','whenScaled':'Retain'},
                    'template':{'metadata':{'labels':{'app':'rabbitmq'}},'spec':{'automountServiceAccountToken':False,
                                'securityContext':{'fsGroup':101},'terminationGracePeriodSeconds':60,'containers':[rabbit]}},
                    'volumeClaimTemplates':[{'metadata':{'name':'data'},'spec':{'accessModes':['ReadWriteOnce'],
                                            'storageClassName':storage_class,'resources':{'requests':{'storage':'2Gi'}}}}]}})
    return items


def render_cluster(config,output='artifacts/eks'):
    out=ROOT/output;out.mkdir(parents=True,exist_ok=True)
    cluster=yaml.safe_load((ROOT/'infra/aws/eksctl.yaml').read_text())
    cluster['metadata'].update(name=config['cluster'],region=config['region'],version=config['kubernetes_version'])
    cluster['availabilityZones']=config['availability_zones'];cluster['vpc']['publicAccessCIDRs']=config['admin_cidrs']
    cluster['managedNodeGroups'][0].update(instanceType=config['node_instance_type'],desiredCapacity=config['nodes'],minSize=config['nodes'])
    (out/'eksctl.rendered.yaml').write_text(yaml.safe_dump(cluster,sort_keys=False))


def render(config,example=False,output='artifacts/eks'):
    lock=json.loads((ROOT/'infra/aws/images.lock.json').read_text())
    ca=(ROOT/'infra/aws/rds-ca-bundle.pem').read_text()
    items=[{'apiVersion':'v1','kind':'Namespace','metadata':{'name':'store'}},
           {'apiVersion':'v1','kind':'Namespace','metadata':{'name':'store-bootstrap'}},
           {'apiVersion':'v1','kind':'ConfigMap','metadata':metadata('store-rds-ca'),'data':{'global-bundle.pem':ca}}]
    items+=dependencies(lock)
    items+=list(yaml.safe_load_all((ROOT/'infra/aws/deployer-rbac.yaml').read_text()))
    for name in SERVICES:
        image=lock[name]['image']
        if not re.fullmatch(r'uyris/store-'+name+r':[a-f0-9]{40}@sha256:[a-f0-9]{64}',image):raise ValueError('Invalid locked image')
        sha=subprocess.check_output(['git','-C',str(ROOT/'api'/name),'rev-parse','HEAD'],text=True).strip()
        if lock[name]['commit']!=sha:raise ValueError('Source pointer differs from lock: '+name)
        documents=list(yaml.safe_load_all((ROOT/'api'/name/'k8s/k8s.yaml').read_text()))
        for doc in documents:
            if doc['kind']=='Deployment':
                spec=doc['spec']['template']['spec'];container=spec['containers'][0];container['image']=image
                if name in ['account','product','order']:
                    spec.setdefault('volumes',[]).append({'name':'rds-ca','configMap':{'name':'store-rds-ca'}})
                    container.setdefault('volumeMounts',[]).append({'name':'rds-ca','mountPath':'/etc/rds-ca','readOnly':True})
            items.append(doc)
    annotations={'alb.ingress.kubernetes.io/scheme':'internet-facing',
        'alb.ingress.kubernetes.io/target-type':'ip','alb.ingress.kubernetes.io/certificate-arn':config['certificate_arn'],
        'alb.ingress.kubernetes.io/listen-ports':'[{"HTTP":80},{"HTTPS":443}]',
        'alb.ingress.kubernetes.io/ssl-redirect':'443','alb.ingress.kubernetes.io/healthcheck-path':'/health-check',
        'alb.ingress.kubernetes.io/subnets':','.join(config['public_subnets']),
        'alb.ingress.kubernetes.io/tags':'project='+config['cluster']}
    items.append({'apiVersion':'networking.k8s.io/v1','kind':'Ingress',
        'metadata':{**metadata('gateway'),'annotations':annotations},
        'spec':{'ingressClassName':'alb','tls':[{'hosts':[config['domain']]}],
                'rules':[{'host':config['domain'],'http':{'paths':[{'path':'/','pathType':'Prefix',
                    'backend':{'service':{'name':'gateway','port':{'number':8000}}}}]}}]}})
    application_kinds={'Deployment','ConfigMap','Service','HorizontalPodAutoscaler','PodDisruptionBudget'}
    applications=[resource for resource in items if resource['kind'] in application_kinds and
                  resource['metadata']['name'] not in ['redis','rabbitmq','rabbitmq-headless']]
    foundation=[resource for resource in items if resource not in applications]
    bootstrap=[{'apiVersion':'v1','kind':'ConfigMap','metadata':metadata('rds-bootstrap-code','store-bootstrap'),
                'data':{'bootstrap.py':(ROOT/'scripts/bootstrap-databases.py').read_text(),'global-bundle.pem':ca}},
        {'apiVersion':'batch/v1','kind':'Job','metadata':metadata('rds-bootstrap','store-bootstrap'),
         'spec':{'backoffLimit':0,'activeDeadlineSeconds':300,'template':{'metadata':{'labels':{'app':'rds-bootstrap'}},
          'spec':{'restartPolicy':'Never','automountServiceAccountToken':False,
           'securityContext':{'runAsNonRoot':True,'runAsUser':10001},
           'containers':[{'name':'bootstrap','image':lock['account']['image'],
             'command':['python','/bootstrap/bootstrap.py'],'envFrom':[{'secretRef':{'name':'rds-bootstrap'}}],
             'env':[{'name':'PGSSLROOTCERT','value':'/bootstrap/global-bundle.pem'}],
             'securityContext':{'readOnlyRootFilesystem':True,'allowPrivilegeEscalation':False,'capabilities':{'drop':['ALL']}},
             'resources':{'requests':{'cpu':'100m','memory':'64Mi'},'limits':{'cpu':'500m','memory':'128Mi'}},
             'volumeMounts':[{'name':'code','mountPath':'/bootstrap','readOnly':True}]}],
           'volumes':[{'name':'code','configMap':{'name':'rds-bootstrap-code'}}]}}}}]
    out=ROOT/output;out.mkdir(parents=True,exist_ok=True)
    render_cluster(config,output)
    for filename,resources in [('release.json',items),('applications.json',applications),
                               ('foundation.json',foundation),('bootstrap.json',bootstrap)]:
        (out/filename).write_text(json.dumps({'apiVersion':'v1','kind':'List','items':resources},indent=2)+'\n')
    (out/'release-metadata.json').write_text(json.dumps({'example_only':example,'config':config,'images':lock,
        'note':'Rendered locally; not evidence of AWS provisioning or successful deployment.'},indent=2)+'\n')
    costs={'region':config['region'],'academic_hours':config['academic_hours'],'monthly_hours':config['monthly_hours'],
        'resources':[{'item':'EKS standard control plane','quantity':1,'unit':'cluster-hour'},
          {'item':'EC2 Linux '+config['node_instance_type'],'quantity':config['nodes'],'unit':'instance-hour'},
          {'item':'Worker gp3 root volumes','quantity':20*config['nodes'],'unit':'GB-month; prorate by hours'},
          {'item':'RDS PostgreSQL Single-AZ '+config['rds_instance_class'],'quantity':1,'unit':'instance-hour'},
          {'item':'RDS gp3','quantity':20,'unit':'GB-month; prorate by hours'},
          {'item':'RabbitMQ EBS gp3','quantity':2,'unit':'GB-month; prorate by hours'},
          {'item':'NAT Gateway','quantity':1,'unit':'gateway-hour + processed GB'},
          {'item':'Application Load Balancer','quantity':1,'unit':'ALB-hour + LCU-hour'},
          {'item':'Public IPv4, data egress, CloudWatch, snapshots/backups, CPU surplus credits','quantity':None,'unit':'measure actual configuration/usage'},
          {'item':'Jenkins host (if dedicated EC2)','quantity':None,'unit':'instance-hour + EBS + network; include only when used'}],
        'pricing_status':'Inputs prepared; enter current region-specific Calculator rates/usage and save a share link or export before provisioning.',
        'quote_url':None,'estimated_total':None}
    (out/'cost-inputs.json').write_text(json.dumps(costs,indent=2)+'\n')
    print('Rendered '+str(len(items))+' resources and separate bootstrap. Example-only='+str(example))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['lock','cluster','render'])
    parser.add_argument('--config',default='infra/aws/deploy.example.json')
    parser.add_argument('--example',action='store_true')
    parser.add_argument('--output',default='artifacts/eks')
    args=parser.parse_args()
    if args.action=='lock':lock_images()
    elif args.action=='cluster':
        render_cluster(load_config(args.config,args.example,cluster_only=True),args.output)
        print('Rendered cluster configuration only; no resources created')
    else:render(load_config(args.config,args.example),args.example,args.output)
