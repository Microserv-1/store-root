"""Write a Git-ignored CloudFormation parameter file; never put passwords in argv/logs."""
import argparse
import json
from pathlib import Path
import re
import subprocess

parser=argparse.ArgumentParser()
parser.add_argument('--vpc',required=True)
parser.add_argument('--private-subnets',nargs=2,required=True)
parser.add_argument('--worker-sg',required=True)
parser.add_argument('--instance-class',choices=['db.t4g.small','db.t4g.medium'],default='db.t4g.small')
parser.add_argument('--engine-version',help='Explicit available PostgreSQL 16 minor, or use --discover-engine')
parser.add_argument('--discover-engine',action='store_true',help='Read available PostgreSQL 16 minors from AWS, without provisioning')
parser.add_argument('--region',default='us-east-1')
parser.add_argument('--env-file',default='.env.eks')
parser.add_argument('--output',default='secrets/rds-parameters.json')
args=parser.parse_args()
if args.discover_engine:
    if args.engine_version:parser.error('Choose explicit version or discovery, not both')
    result=json.loads(subprocess.check_output(['aws','rds','describe-db-engine-versions','--engine','postgres','--region',args.region,'--output','json']))
    versions=[item['EngineVersion'] for item in result['DBEngineVersions'] if item.get('Status')=='available' and re.fullmatch(r'16\.[0-9]+',item['EngineVersion'])]
    if not versions:parser.error('No available PostgreSQL 16 minor found in the target region')
    args.engine_version=max(versions,key=lambda value:int(value.split('.')[1]))
if not args.engine_version or not re.fullmatch(r'16\.[0-9]+',args.engine_version):
    parser.error('Provide an available PostgreSQL 16 minor or use --discover-engine')
for value,prefix in [(args.vpc,'vpc'),(args.worker_sg,'sg'),*((s,'subnet') for s in args.private_subnets)]:
    if not re.fullmatch(prefix+r'-[a-f0-9]{8,17}',value):parser.error('Invalid infrastructure identifier')
if len(set(args.private_subnets))!=2:parser.error('Use two distinct private subnets')
for path in [args.env_file,args.output]:
    if subprocess.run(['git','check-ignore','--quiet',path],check=False).returncode!=0:
        parser.error('Secret input/output paths must be ignored by Git')
env=dict(line.split('=',1) for line in Path(args.env_file).read_text().splitlines() if line and not line.startswith('#'))
password=env.get('PGPASSWORD','')
if not re.fullmatch(r'[a-f0-9]{64}',password):parser.error('Generate EKS credentials before preparing RDS parameters')
values={'VpcId':args.vpc,'PrivateSubnets':','.join(args.private_subnets),'WorkerSecurityGroup':args.worker_sg,
        'DatabaseInstanceClass':args.instance_class,'DatabaseEngineVersion':args.engine_version,'DatabasePassword':password}
output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
output.write_text(json.dumps([{'ParameterKey':k,'ParameterValue':v} for k,v in values.items()],indent=2)+'\n')
print('Wrote ignored RDS parameter file. Supply it with --parameters file://'+str(output)+'; do not publish it.')
