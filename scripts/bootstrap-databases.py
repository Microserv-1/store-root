"""Idempotent database/role bootstrap, run only by the operator, never the CI deployer.

Requires psycopg 3 (already present in Account's image). Passwords enter via
environment/Secret; SQL identifiers and values use psycopg composables.
"""
import os
import sys
import psycopg
from psycopg import sql

DATABASES=[('accounts','account_app','ACCOUNT_DB_PASSWORD'),
           ('products','product_app','PRODUCT_DB_PASSWORD'),
           ('orders','order_app','ORDER_DB_PASSWORD')]


def connection(user=None,password=None,database='postgres'):
    return psycopg.connect(host=os.environ['PGHOST'],port=os.environ.get('PGPORT','5432'),
        dbname=database,user=user or os.environ['PGUSER'],
        password=password or os.environ['PGPASSWORD'],
        sslmode=os.environ.get('PGSSLMODE','require'),connect_timeout=10,autocommit=True)


def main():
    for _,_,key in DATABASES:
        if len(os.environ.get(key,''))<32:raise ValueError('Missing strong application password: '+key)
    with connection() as admin:
        for database,role,key in DATABASES:
            if not admin.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(role,)).fetchone():
                admin.execute(sql.SQL('CREATE ROLE {} LOGIN').format(sql.Identifier(role)))
            flags=admin.execute('SELECT rolsuper,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=%s',(role,)).fetchone()
            if any(flags):raise RuntimeError('Refusing to reuse an elevated application role: '+role)
            # RDS master users are not SQL superusers and cannot change the
            # SUPERUSER attribute. New roles already default to no superuser/
            # replication/bypass RLS; existing elevated roles are rejected above.
            admin.execute(sql.SQL('ALTER ROLE {} WITH LOGIN NOCREATEDB NOCREATEROLE PASSWORD {}').format(
                sql.Identifier(role),sql.Literal(os.environ[key])))
            # PostgreSQL 16 requires SET membership to CREATE DATABASE OWNER.
            # Membership goes to the operator, never from the app to the admin.
            admin.execute(sql.SQL('GRANT {} TO {} WITH INHERIT FALSE, SET TRUE').format(
                sql.Identifier(role),sql.Identifier(os.environ['PGUSER'])))
            if not admin.execute('SELECT 1 FROM pg_database WHERE datname=%s',(database,)).fetchone():
                admin.execute(sql.SQL('CREATE DATABASE {} OWNER {}').format(sql.Identifier(database),sql.Identifier(role)))
            owner=admin.execute('SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=%s',(database,)).fetchone()[0]
            if owner!=role:
                raise RuntimeError('Existing database has another owner; migrate explicitly: '+database)
            # Run ownership/ACL operations as the actual database owner, without
            # relying on superuser access or inherited privileges of the master.
            with connection(role,os.environ[key],database) as db:
                db.execute(sql.SQL('REVOKE ALL ON DATABASE {} FROM PUBLIC').format(sql.Identifier(database)))
                db.execute('REVOKE ALL ON SCHEMA public FROM PUBLIC')
                db.execute(sql.SQL('ALTER SCHEMA public OWNER TO {}').format(sql.Identifier(role)))
    for database,role,key in DATABASES:
        with connection(role,os.environ[key],database) as app:
            # Rolled back transaction: validates application DDL/DML without leaving a table.
            with app.transaction(force_rollback=True):
                app.execute('CREATE TABLE public.store_bootstrap_probe (id integer PRIMARY KEY)')
                app.execute('INSERT INTO public.store_bootstrap_probe VALUES (1)')
                assert app.execute('SELECT count(*) FROM public.store_bootstrap_probe').fetchone()[0]==1
        for other,_,_ in DATABASES:
            if other==database:continue
            try:
                with connection(role,os.environ[key],other):pass
            except psycopg.OperationalError as exc:
                # libpq reports startup FATALs as OperationalError; SQLSTATE is
                # not always available before a connection is established.
                if exc.sqlstate=='42501' or 'permission denied for database' in str(exc):continue
                raise
            except psycopg.errors.InsufficientPrivilege:continue
            raise RuntimeError('Unexpected cross-database access: '+role+' -> '+other)
        print('PASS: own database DDL/DML and cross-database isolation: '+role)


if __name__=='__main__':
    try:main()
    except Exception as exc:
        # Connection exceptions can contain addresses/users; do not dump secrets.
        state=getattr(exc,'sqlstate',None)
        print('Database bootstrap failed: '+type(exc).__name__+(' SQLSTATE='+state if state else ''),file=sys.stderr)
        sys.exit(1)
