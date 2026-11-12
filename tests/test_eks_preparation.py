"""Guards against preparing an unintended target or leaking the master credential."""
import base64
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/(name+'.py'))
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


prepare=module('prepare-eks');secret_inputs=module('eks-secrets');release=module('eks-apply')


class PreparationGuards(unittest.TestCase):
    def config(self,**changes):
        data=json.loads((ROOT/'infra/aws/deploy.example.json').read_text())
        data.update(account_id='111122223333',domain='api.store.invalid',admin_cidrs=['8.8.8.8/32'],
                    public_subnets=['subnet-1234567890abcdef0','subnet-abcdef12345678900'],
                    certificate_arn='arn:aws:acm:us-east-1:111122223333:certificate/11111111-2222-3333-4444-555555555555')
        data.update(changes)
        return data

    def load(self,data,**options):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'config.json';path.write_text(json.dumps(data))
            return prepare.load_config(path,**options)

    def test_documentation_values_cannot_become_real_release(self):
        example=json.loads((ROOT/'infra/aws/deploy.example.json').read_text())
        with self.assertRaises(ValueError):self.load(example)
        self.load(example,example=True)

    def test_unrestricted_operator_access_is_rejected(self):
        with self.assertRaises(ValueError):self.load(self.config(admin_cidrs=['0.0.0.0/0']))

    def test_certificate_in_another_account_is_rejected(self):
        with self.assertRaises(ValueError):self.load(self.config(certificate_arn='arn:aws:acm:us-east-1:999999999999:certificate/11111111-2222-3333-4444-555555555555'))

    def test_duplicate_subnets_are_rejected(self):
        with self.assertRaises(ValueError):self.load(self.config(public_subnets=['subnet-1234567890abcdef0']*2))

    def test_cluster_can_be_prepared_before_subnets_and_certificate_exist(self):
        data=self.config(public_subnets=[],certificate_arn='',domain='')
        self.load(data,cluster_only=True)
        with self.assertRaises(ValueError):self.load(data)

    def test_master_password_never_enters_the_application_secret(self):
        values={key:f'{index:064x}' for index,key in enumerate(secret_inputs.KEYS,1)}
        values.update(PGHOST='test.abcdef.us-east-1.rds.amazonaws.com',PGPORT='5432',PGUSER='store',PGSSLMODE='verify-full')
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'input.env';path.write_text(''.join(k+'='+v+'\n' for k,v in values.items()))
            app,bootstrap=secret_inputs.resources(path)
        data={k:base64.b64decode(v).decode() for k,v in app['data'].items()}
        self.assertFalse(any(values['PGPASSWORD'] in value for value in data.values()))
        self.assertNotIn('PGPASSWORD',data);self.assertIn('PGPASSWORD',bootstrap['data'])
        for key,role in [('DATABASE_URL','account_app'),('PRODUCT_DATABASE_URL','product_app'),('ORDER_DATABASE_URL','order_app')]:
            self.assertIn('://'+role+':',data[key]);self.assertIn('sslmode=verify-full',data[key])

    def test_release_cannot_apply_secrets_or_another_namespace(self):
        secret={'kind':'Secret','metadata':{'name':'account','namespace':'store'}}
        with self.assertRaises(ValueError):release.validate_resources([secret],{('Secret','account')})
        deployment={'kind':'Deployment','metadata':{'name':'account','namespace':'default'}}
        with self.assertRaises(ValueError):release.validate_resources([deployment],{('Deployment','account')})


if __name__=='__main__':unittest.main()
