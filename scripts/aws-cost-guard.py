"""Read-only inventory guard. Never calls Cost Explorer or changes AWS resources.

This is a point-in-time configuration check, not a billing cap or a background
monitor. Existing resources keep accruing costs even when all checks pass.
"""
import argparse
import datetime
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile')
    parser.add_argument('--context', default='store-eks')
    parser.add_argument('--config', default='.env.eks.json')
    parser.add_argument('--output', default='artifacts/eks/cost-guard.json')
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding='utf-8'))

    def aws(*words):
        command = ['aws', *words, '--region', config['region'], '--output', 'json', '--no-cli-pager']
        if args.profile:
            command += ['--profile', args.profile]
        return json.loads(subprocess.check_output(command, text=True))

    def kube(*words):
        return json.loads(subprocess.check_output(
            ['kubectl', '--context', args.context, *words, '-o', 'json'], text=True))

    identity = aws('sts', 'get-caller-identity')
    if identity['Account'] != config['account_id']:
        raise ValueError('Unexpected AWS account')
    cluster = aws('eks', 'describe-cluster', '--name', config['cluster'])['cluster']
    vpc = cluster['resourcesVpcConfig']['vpcId']
    kubeconfig = kube('config', 'view', '--minify')
    if kubeconfig['clusters'][0]['cluster']['server'] != cluster['endpoint']:
        raise ValueError('Kubernetes context points at another cluster')
    nodegroup = aws('eks', 'describe-nodegroup', '--cluster-name', config['cluster'],
                    '--nodegroup-name', 'application')['nodegroup']
    instances = aws('ec2', 'describe-instances', '--filters', 'Name=vpc-id,Values=' + vpc,
                    'Name=instance-state-name,Values=running')['Reservations']
    machines = [{'id': i['InstanceId'], 'type': i['InstanceType']}
                for reservation in instances for i in reservation['Instances']]
    deployments = kube('get', 'deployments', '-A')['items']
    scalers = [d['metadata']['name'] for d in deployments
               if any(key in json.dumps(d['spec']).lower()
                      for key in ('cluster-autoscaler', 'karpenter'))]
    hpas = kube('-n', 'store', 'get', 'hpa')['items']
    services = kube('-n', 'store', 'get', 'services')['items']
    problems = []
    if len(machines) != 3 or any(i['type'] != 't3.large' for i in machines):
        problems.append('Running VPC instances differ from the reviewed baseline: three t3.large')
    if nodegroup['scalingConfig']['desiredSize'] != 2:
        problems.append('Worker desired capacity differs from two')
    if scalers:
        problems.append('Node autoscaler controller detected; review node cost exposure')
    if cluster.get('computeConfig', {}).get('enabled'):
        problems.append('EKS Auto Mode enabled; review cost exposure')
    if any(s['spec'].get('type') == 'LoadBalancer' for s in services):
        problems.append('Application LoadBalancer Service found in the private-access setup')
    if any(h['spec']['maxReplicas'] > 5 for h in hpas):
        problems.append('An application HPA permits more than five replicas')
    result = {
        'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'cluster': config['cluster'], 'region': config['region'],
        'running_vpc_instances': machines, 'worker_scaling': nodegroup['scalingConfig'],
        'node_autoscaler_deployments': scalers,
        'hpas': [{'name': h['metadata']['name'], 'min': h['spec']['minReplicas'],
                  'max': h['spec']['maxReplicas'], 'current': h.get('status', {}).get('currentReplicas')}
                 for h in hpas],
        'status': 'REVIEW_REQUIRED' if problems else 'BASELINE_MATCHES', 'findings': problems,
        'limitations': [
            'Not a real-time monitor, billing measurement, hard budget or automatic shutdown.',
            'Worker maxSize remains an allowed ceiling, not proof that nodes will be added.',
            'CPU surplus credits, NAT traffic, logs, storage and existing resources can still incur costs.',
            'No load, resource mutation or Cost Explorer API call is performed.'
        ]
    }
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(result['status'] + ': ' + str(len(machines)) + ' running VPC instances; workers=' +
          str(nodegroup['scalingConfig']['desiredSize']) + '; node autoscalers=' + str(len(scalers)))
    for problem in problems:
        print('REVIEW: ' + problem)
    return 2 if problems else 0


if __name__ == '__main__':
    raise SystemExit(main())
