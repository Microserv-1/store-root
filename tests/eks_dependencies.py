"""Exercise generated Redis/RabbitMQ workloads in an OWNED isolated Kind namespace.

Uses Kind standard storage instead of AWS EBS. Never touches the store broker.
Requires requirements-ops.txt. Cleans only a namespace with this run's label.
"""
import base64
import importlib.util
import json
from pathlib import Path
import secrets
import subprocess
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('prepare',ROOT/'scripts/prepare-eks.py')
prepare=importlib.util.module_from_spec(spec);spec.loader.exec_module(prepare)
context='kind-microserv-store';run_id=uuid.uuid4().hex;namespace='store-eks-prep-'+run_id[:8]


def kubectl(*args,document=None,source=None):
    process=subprocess.run(['kubectl','--context',context,*args],
        input=json.dumps(document) if document else source,capture_output=True,text=True)
    if process.returncode:raise RuntimeError(process.stderr)
    return process.stdout


def wait_pod(app,previous_uid=None):
    for attempt in range(120):
        pods=json.loads(kubectl('-n',namespace,'get','pods','-l','app='+app,'-o','json'))['items']
        for pod in pods:
            if pod['metadata']['uid']==previous_uid or pod['metadata'].get('deletionTimestamp'):continue
            if any(c['type']=='Ready' and c['status']=='True' for c in pod.get('status',{}).get('conditions',[])):
                return pod
        time.sleep(2)
    raise RuntimeError('Timed out waiting for isolated '+app)


def client(source):
    return kubectl('-n',namespace,'exec','-i','client','--','python','-',source=source)


created=False
try:
    lock=json.loads((ROOT/'infra/aws/images.lock.json').read_text())
    resources=[{'apiVersion':'v1','kind':'Namespace','metadata':{'name':namespace,'labels':{'store-prep-run':run_id}}}]
    passwords={key:secrets.token_hex(32) for key in ['REDIS_PASSWORD','RABBITMQ_PASSWORD']}
    resources.append({'apiVersion':'v1','kind':'Secret','metadata':{'name':'store-secrets','namespace':namespace},
                      'data':{key:base64.b64encode(value.encode()).decode() for key,value in passwords.items()}})
    for resource in prepare.dependencies(lock,storage_class='standard'):
        if resource['kind']=='StorageClass':continue
        resource['metadata']['namespace']=namespace;resources.append(resource)
    resources.append({'apiVersion':'v1','kind':'Pod','metadata':{'name':'client','namespace':namespace,'labels':{'app':'client'}},
        'spec':{'automountServiceAccountToken':False,'containers':[{'name':'client','image':lock['order']['image'],
          'command':['python','-c','import time;time.sleep(1800)'],
          'envFrom':[{'secretRef':{'name':'store-secrets'}}],
          'resources':{'requests':{'cpu':'50m','memory':'32Mi'},'limits':{'cpu':'500m','memory':'128Mi'}}}]}})
    # Namespace must exist before a List containing namespaced resources is applied.
    kubectl('apply','-f','-',document=resources[0]);created=True
    kubectl('apply','-f','-',document={'apiVersion':'v1','kind':'List','items':resources[1:]})
    wait_pod('client');redis=wait_pod('redis');rabbit=wait_pod('rabbitmq')
    print('Isolated generated dependencies are ready',flush=True)
    prefix='''import os,pika,socket
def broker():
 return pika.BlockingConnection(pika.ConnectionParameters(host='rabbitmq',credentials=pika.PlainCredentials('store',os.environ['RABBITMQ_PASSWORD'])))
def redis(command):
 s=socket.create_connection(('redis',6379),timeout=5);r=s.makefile('rb')
 s.sendall(('AUTH '+os.environ['REDIS_PASSWORD']+'\\r\\n').encode());assert r.readline()==b'+OK\\r\\n'
 s.sendall((command+'\\r\\n').encode());result=r.readline();s.close();return result
'''
    message=run_id
    client(prefix+f'''
conn=broker();ch=conn.channel();ch.queue_declare(queue='prep.persistence',durable=True);ch.confirm_delivery()
ch.basic_publish(exchange='',routing_key='prep.persistence',body={message!r}.encode(),mandatory=True,properties=pika.BasicProperties(delivery_mode=2));conn.close()
assert redis('SET prep-key present EX 300')==b'+OK\\r\\n'
print('PASS: persistent queue message and cache fixture created')
''')
    pvc=json.loads(kubectl('-n',namespace,'get','pvc','data-rabbitmq-0','-o','json'))['metadata']['uid']
    kubectl('-n',namespace,'delete','pod',rabbit['metadata']['name'],'--wait=true')
    wait_pod('rabbitmq',rabbit['metadata']['uid'])
    after=json.loads(kubectl('-n',namespace,'get','pvc','data-rabbitmq-0','-o','json'))['metadata']['uid']
    assert pvc==after
    client(prefix+f'''
conn=broker();ch=conn.channel();method,props,body=ch.basic_get('prep.persistence',auto_ack=False)
assert method is not None and body=={message!r}.encode();ch.basic_ack(method.delivery_tag);conn.close()
print('PASS: durable message survived broker pod replacement on the same PVC')
''')
    print('PASS: RabbitMQ persisted its confirmed durable message after pod replacement',flush=True)
    kubectl('-n',namespace,'delete','pod',redis['metadata']['name'],'--wait=true')
    wait_pod('redis',redis['metadata']['uid'])
    client(prefix+"assert redis('GET prep-key')==b'$-1\\r\\n'\nprint('PASS: restarted cache is empty and available')\n")
    report={'context':context,'namespace':namespace,'storage_class':'standard (Kind local-path)',
            'rabbitmq':'confirmed durable message recovered after pod replacement; PVC UID unchanged',
            'redis':'ephemeral cache cold-start verified after pod replacement',
            'limits':'Does not validate AWS EBS driver, AZ rescheduling, snapshots or multi-node broker HA.'}
    (ROOT/'artifacts/eks-dependencies.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS: isolated dependency recovery checks',flush=True)
finally:
    if created:
        own=json.loads(kubectl('get','namespace',namespace,'-o','json'))
        if own['metadata']['labels'].get('store-prep-run')!=run_id:raise RuntimeError('Refusing to clean a namespace owned by another run')
        kubectl('delete','namespace',namespace,'--wait=false')
