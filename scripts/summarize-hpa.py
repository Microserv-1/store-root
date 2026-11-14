"""Summarize captured evidence and plot it locally. Never contacts AWS or starts load."""
import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import re

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates


def utc(value):
    return dt.datetime.strptime(value, 'UTC %Y-%m-%d %H:%M:%S').replace(tzinfo=dt.timezone.utc)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', required=True)
    args = parser.parse_args()
    folder = Path(args.directory)
    samples = json.loads((folder / 'recorded-hpa.json').read_text())
    load = json.loads((folder / 'login-load.json').read_text())
    prom = json.loads((folder / 'prometheus-during.json').read_text())
    times, replicas, ready = [], [], []
    for sample in samples:
        account = next(h for h in sample['hpa_status'] if h['name'] == 'account')
        row = re.search(r'^account\s+(\d+)/(\d+)\s+(\d+)\s+(\d+)\b', sample['DEPLOYMENTS'], re.M)
        if not row:
            raise ValueError('Account readiness missing from a captured snapshot')
        times.append(utc(sample['utc']))
        replicas.append(account['current'])
        ready.append(int(row.group(1)))
    served = {}
    cpu = {}
    for name, output in [('credential_verification_rps', served), ('account_cpu_cores', cpu)]:
        for series in prom['queries'][name]['response']['data']['result']:
            values = [float(v) for _, v in series['values'] if math.isfinite(float(v))]
            output[series['metric']['pod']] = max(values) if values else 0
    served = {pod: value for pod, value in served.items() if value > 0}
    scale_up = next((samples[i]['utc'] for i, n in enumerate(ready) if n > ready[0]), None)
    scale_down = next((s['utc'] for i, s in enumerate(samples)
                       if scale_up and utc(s['utc']) > utc(scale_up) and ready[i] == ready[0]
                       and s['load_status'].startswith('FINISHED')), None)
    result = {
        'context': samples[0]['context'], 'baseline_replicas': replicas[0],
        'baseline_ready': ready[0],
        'initial_hpa_status_matches_deployment': replicas[0] == ready[0],
        'peak_replicas': max(replicas), 'peak_ready': max(ready),
        'final_replicas': replicas[-1], 'final_ready': ready[-1],
        'first_additional_ready_utc': scale_up, 'first_return_to_baseline_utc': scale_down,
        'requests': load['requests'], 'error_ratio': load['error_ratio'],
        'requests_per_second': load['requests_per_second'], 'latency_ms': load['latency_ms'],
        'credential_verification_pods': served, 'peak_cpu_cores_by_pod': cpu,
        'commits': load['commits'],
        'source_sha256': {name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
                          for name in ('recorded-hpa.json', 'login-load.json', 'prometheus-during.json')},
        'limits': [
            'One 4-user login run, not a controlled comparison or a business-load benchmark.',
            'Client latency includes the authenticated port-forward/network path.',
            'Gateway tunnel pins one Gateway pod; Account distribution is proved by per-pod metrics.',
            'HPA CPU percentage is relative to requests, not machine-wide CPU percentage.',
            'No monthly availability, uniform distribution or unlimited capacity is established.',
            'HPA status and Deployment are sampled sequentially and can disagree during reconciliation; the ready-cycle uses Deployment readiness and requires the final HPA count to agree.'
        ]
    }
    result['scale_cycle_observed'] = bool(scale_up and scale_down and max(ready) > ready[0]
                                         and replicas[-1] == ready[0] and ready[-1] == ready[0])
    (folder / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')

    end = dt.datetime.fromisoformat(load['timestamp_utc'].replace('Z', '+00:00'))
    start = end - dt.timedelta(seconds=load['actual_duration_s'])
    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True, constrained_layout=True)
    axes[0].step(times, replicas, where='post', label='HPA: réplicas atuais', color='#006b89', linewidth=2)
    axes[0].step(times, ready, where='post', label='Deployment: réplicas prontas', color='#cb6d19', linestyle='--')
    axes[0].set_ylabel('Réplicas Account')
    axes[0].set_yticks(range(0, max(ready) + 2))
    axes[0].legend(loc='upper right', fontsize=9)
    pod_names = sorted(cpu)
    colors = {pod: plt.get_cmap('tab10')(i % 10) for i, pod in enumerate(pod_names)}
    for axis, query, ylabel in [(axes[1], 'account_cpu_cores', 'CPU por pod (cores)'),
                                (axes[2], 'credential_verification_rps', 'Verificações/s por pod')]:
        for series in prom['queries'][query]['response']['data']['result']:
            points = [(dt.datetime.fromtimestamp(float(t), dt.timezone.utc), float(v))
                      for t, v in series['values'] if math.isfinite(float(v))]
            points = [(t, v) for t, v in points if times[0] <= t <= times[-1]]
            if points:
                axis.plot([p[0] for p in points], [p[1] for p in points],
                          label=series['metric']['pod'].rsplit('-', 1)[-1], linewidth=1.5,
                          color=colors[series['metric']['pod']])
        axis.set_ylabel(ylabel)
        axis.legend(title='Sufixo do pod', fontsize=8, title_fontsize=8, loc='upper right')
    for axis in axes:
        axis.axvspan(start, end, color='#bad6e5', alpha=.4)
        axis.grid(alpha=.2)
        axis.set_xlim(times[0], times[-1])
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S', tz=dt.timezone.utc))
    axes[-1].set_xlabel('Horário UTC em ' + times[0].strftime('%d/%m/%Y') + '. Faixa azul: carga de login aproximada.')
    title = ('Account: ' + str(ready[0]) + ' réplicas prontas na baseline, pico de ' +
             str(max(ready)) + ', final ' + str(ready[-1]) + '\n' + str(load['users']) +
             ' usuários, ' + str(load['requested_duration_s']) + ' s, ' + str(load['requests']) +
             ' requisições; nenhum ganho antes/depois é inferido')
    fig.suptitle(title, fontsize=14)
    fig.savefig(folder / 'hpa-analysis.png', dpi=150)
    plt.close(fig)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
