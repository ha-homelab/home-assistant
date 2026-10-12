#!/usr/bin/env python3
"""First installation only: register this organization's dedicated k3s runners.

Run from an authorized workstation with gh, kubectl and PyYAML. Registration
tokens travel only over process stdin; no account token is stored in Kubernetes.
"""
import json
from pathlib import Path
import subprocess
import yaml

ORG = 'ha-homelab'
NAMESPACES = ('github-actions-ha-ci', 'github-actions-ha-metadata')
NAMES = ('mp-ha-ci-1-k3s', 'mp-ha-ci-2-k3s', 'mp-ha-metadata-1-k3s')


def run(args, data=None):
    return subprocess.run(args, input=data, text=True, capture_output=True, check=True).stdout


def main():
    group = json.loads(run(['gh', 'api', f'orgs/{ORG}/actions/runner-groups/1']))
    if group['name'] != 'Default' or group['allows_public_repositories']:
        raise SystemExit('Default runner group must exclude all public repositories')
    pages = json.loads(run(['gh', 'api', '--paginate', '--slurp', f'orgs/{ORG}/actions/runners?per_page=100']))
    if any(r['name'] in NAMES for page in pages for r in page['runners']):
        raise SystemExit('Runner already registered; inspect existing installation instead')
    for ns in NAMESPACES:
        existing = run(['kubectl', 'get', 'namespace', ns, '--ignore-not-found', '-o', 'name'])
        if existing.strip():
            raise SystemExit(f'{ns} already exists; inspect before changing it')
    docs = list(yaml.safe_load_all(Path(__file__).with_name('runners.yaml').read_text()))
    desired_replicas = {
        (doc['metadata']['namespace'], doc['metadata']['name']): doc['spec']['replicas']
        for doc in docs if doc['kind'] == 'Deployment'
    }
    for doc in docs:
        if doc['kind'] == 'Deployment':
            doc['spec']['replicas'] = 0
    print(run(['kubectl', 'apply', '-f', '-'], yaml.safe_dump_all(docs)), end='')
    # Namespace creation must precede the server-side validation of its objects.
    run(['kubectl', 'apply', '--dry-run=server', '-f', str(Path(__file__).with_name('runners.yaml'))])
    token = json.loads(run(['gh', 'api', '--method', 'POST', f'orgs/{ORG}/actions/runners/registration-token']))['token']
    for ns in NAMESPACES:
        secret = dict(apiVersion='v1', kind='Secret', metadata=dict(name='runner-bootstrap', namespace=ns), stringData={'RUNNER_TOKEN': token})
        run(['kubectl', 'create', '-f', '-'], json.dumps(secret))
    for doc in docs:
        if doc['kind'] == 'Deployment':
            meta = doc['metadata']
            replicas = desired_replicas[(meta['namespace'], meta['name'])]
            print(run(['kubectl', '-n', meta['namespace'], 'scale', 'deployment', meta['name'], f'--replicas={replicas}']), end='')
    print('After the active CI and metadata runners are online, delete runner-bootstrap in both namespaces.')


if __name__ == '__main__':
    main()
