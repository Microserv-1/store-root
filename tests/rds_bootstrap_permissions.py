"""Regression: bootstrap with CREATEDB/CREATEROLE, WITHOUT PostgreSQL superuser.

Uses only a uniquely named disposable local Docker network/database. Never
connects to RDS or reads .env.eks credentials. Requires the local Account image.
"""
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
run_id=uuid.uuid4().hex[:10];network='store-rds-qa-'+run_id;database=network+'-db'
network_created=False;database_created=False
account_image=json.loads((ROOT/'infra/aws/images.lock.json').read_text())['account']['image']
values={key:secrets.token_hex(32) for key in ['PGPASSWORD','ACCOUNT_DB_PASSWORD','PRODUCT_DB_PASSWORD','ORDER_DB_PASSWORD']}
admin_password=secrets.token_hex(32)
values.update(PGHOST=database,PGPORT='5432',PGUSER='store',PGSSLMODE='disable')


def python_in_client(source,environment):
    prefix='import os,json\nos.environ.update(json.loads('+repr(json.dumps(environment))+'))\n'
    subprocess.run(['docker','run','--rm','-i','--network',network,'--entrypoint','python',account_image,'-'],
        input=prefix+source,text=True,check=True)


try:
    subprocess.run(['docker','network','create',network],check=True,stdout=subprocess.DEVNULL);network_created=True
    subprocess.run(['docker','run','--detach','--rm','--name',database,'--network',network,'--env','POSTGRES_PASSWORD','postgres:16-alpine'],
        env=dict(os.environ,POSTGRES_PASSWORD=admin_password),check=True,stdout=subprocess.DEVNULL);database_created=True
    for attempt in range(60):
        if subprocess.run(['docker','exec',database,'pg_isready','-h','127.0.0.1','-U','postgres'],capture_output=True).returncode==0:break
        time.sleep(1)
    else:raise RuntimeError('Local regression database did not become ready')
    seed='''
import psycopg
from psycopg import sql
with psycopg.connect(host=os.environ['PGHOST'],user='postgres',password=os.environ['PGPASSWORD'],dbname='postgres',sslmode='disable',autocommit=True) as db:
 db.execute(sql.SQL('CREATE ROLE store WITH LOGIN CREATEDB CREATEROLE PASSWORD {}').format(sql.Literal(os.environ['OPERATOR_PASSWORD'])))
'''
    python_in_client(seed,dict(values,PGPASSWORD=admin_password,OPERATOR_PASSWORD=values['PGPASSWORD']))
    probe='''
import psycopg
with psycopg.connect(host=os.environ['PGHOST'],user='store',password=os.environ['PGPASSWORD'],dbname='postgres',sslmode='disable',autocommit=True) as db:
 assert db.execute('SELECT rolsuper FROM pg_roles WHERE rolname=current_user').fetchone()[0] is False
 db.execute('CREATE ROLE attribute_probe LOGIN')
 try:db.execute('ALTER ROLE attribute_probe NOSUPERUSER NOREPLICATION')
 except psycopg.errors.InsufficientPrivilege:print('PASS: non-superuser fixture reproduces the forbidden attribute change')
 else:raise AssertionError('Fixture did not reproduce the PostgreSQL privilege restriction')
'''
    python_in_client(probe,values)
    source=(ROOT/'scripts/bootstrap-databases.py').read_text()
    for attempt in range(2):python_in_client(source,values)
    result={'administrator_sql_superuser':False,'administrator_permissions':['CREATEDB','CREATEROLE'],
            'idempotent_runs':2,'own_database_ddl_dml':3,'cross_database_denials_per_run':6,
            'old_superuser_attribute_change':'rejected by fixture as expected',
            'bootstrap_sha256':hashlib.sha256(source.encode()).hexdigest(),'client_image':account_image,
            'limits':'Local PostgreSQL 16 regression with minimum admin permissions; real RDS/TLS bootstrap still to execute.'}
    (ROOT/'artifacts/rds-bootstrap-permissions.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS: bootstrap and repeat execution with a non-superuser administrator')
finally:
    if database_created:subprocess.run(['docker','stop',database],check=True,stdout=subprocess.DEVNULL)
    if network_created:subprocess.run(['docker','network','rm',network],check=True,stdout=subprocess.DEVNULL)
