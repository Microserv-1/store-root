"""Create ignored EKS secrets or send them to an explicit cluster via stdin.

Bootstrap credentials live in a separate namespace; no master password is put
in store-secrets. Never print a Secret or connection string.
"""
import argparse
import base64
import json
import importlib.util
from pathlib import Path
import re
import secrets
import subprocess
from urllib.parse import quote

KEYS=['JWT_SECRET','INTERNAL_AUTH_KEY','GRAFANA_PASSWORD','ACCOUNT_DB_PASSWORD',
      'PRODUCT_DB_PASSWORD','ORDER_DB_PASSWORD','REDIS_PASSWORD','RABBITMQ_PASSWORD','PGPASSWORD']


def generate(path):
    if path.exists():raise ValueError('Refusing to overwrite existing credentials')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text('# Ignored local file. Set the real private RDS endpoint before applying.\n'
        'PGHOST=\nPGPORT=5432\nPGUSER=store\nPGSSLMODE=verify-full\n'+
        ''.join(key+'='+secrets.token_hex(32)+'\n' for key in KEYS),encoding='utf-8')
    print('Created ignored credentials file; no secret values printed')


def resources(path):
    values=dict(line.split('=',1) for line in path.read_text().splitlines() if line and not line.startswith('#'))
    for key in KEYS:
        if not re.fullmatch(r'[a-f0-9]{64}',values.get(key,'')):raise ValueError('Expected generated 64-character hex secret: '+key)
    host=values.get('PGHOST','')
    if not re.fullmatch(r'[a-zA-Z0-9.-]+\.rds\.amazonaws\.com',host):raise ValueError('Set a real private RDS endpoint in PGHOST')
    if values.get('PGSSLMODE')!='verify-full' or values.get('PGUSER')!='store' or values.get('PGPORT')!='5432':
        raise ValueError('Unexpected RDS connection configuration')
    urls={}
    for key,user,database,password in [('DATABASE_URL','account_app','accounts','ACCOUNT_DB_PASSWORD'),
        ('PRODUCT_DATABASE_URL','product_app','products','PRODUCT_DB_PASSWORD'),('ORDER_DATABASE_URL','order_app','orders','ORDER_DB_PASSWORD')]:
        urls[key]=f'postgresql+psycopg://{user}:{quote(values[password],safe="")}@{host}:5432/{database}?sslmode=verify-full&sslrootcert=/etc/rds-ca/global-bundle.pem'
    application={key:values[key] for key in ['JWT_SECRET','INTERNAL_AUTH_KEY','GRAFANA_PASSWORD','REDIS_PASSWORD','RABBITMQ_PASSWORD']}
    application.update(urls)
    application.update(REDIS_URL='redis://:'+values['REDIS_PASSWORD']+'@redis:6379/0',
                       RABBITMQ_URL='amqp://store:'+values['RABBITMQ_PASSWORD']+'@rabbitmq:5672/%2F')
    bootstrap={key:values[key] for key in ['PGHOST','PGPORT','PGUSER','PGPASSWORD','PGSSLMODE','ACCOUNT_DB_PASSWORD','PRODUCT_DB_PASSWORD','ORDER_DB_PASSWORD']}
    def secret(name,namespace,data):
        return {'apiVersion':'v1','kind':'Secret','metadata':{'name':name,'namespace':namespace},'type':'Opaque',
                'data':{k:base64.b64encode(v.encode()).decode() for k,v in data.items()}}
    return secret('store-secrets','store',application),secret('rds-bootstrap','store-bootstrap',bootstrap)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['generate','check','apply-app','apply-bootstrap'])
    parser.add_argument('--env-file',default='.env.eks')
    parser.add_argument('--context')
    parser.add_argument('--config',default='.env.eks.json')
    args=parser.parse_args();path=Path(args.env_file)
    # Do not accidentally generate secrets in a tracked location.
    ignored=subprocess.run(['git','check-ignore','--quiet',str(path)],check=False).returncode==0
    if not ignored:parser.error('The credentials file must be ignored by Git')
    if args.action=='generate':generate(path)
    else:
        app,bootstrap=resources(path)
        if args.action=='check':print('PASS: secret inputs valid; master credential separated from applications')
        else:
            if not args.context:parser.error('An explicit --context is required')
            spec=importlib.util.spec_from_file_location('preflight',Path(__file__).resolve().parent/'eks-preflight.py')
            preflight=importlib.util.module_from_spec(spec);spec.loader.exec_module(preflight)
            config=preflight.prepare.load_config(args.config)
            preflight.target_only(config,args.context)
            chosen=app if args.action=='apply-app' else bootstrap
            subprocess.run(['kubectl','--context',args.context,'apply','-f','-'],input=json.dumps(chosen),text=True,check=True)
