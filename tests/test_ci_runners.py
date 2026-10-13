"""Keep public CI off private runners and preserve legacy runner isolation."""
from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]


class RunnerBoundaryTests(unittest.TestCase):
    def test_public_jobs_use_hosted_runners_without_credentials(self):
        for path in (ROOT / '.github/workflows').glob('*.yml'):
            workflow = yaml.safe_load(path.read_text())
            expected = ({'contents': 'read', 'actions': 'read', 'pull-requests': 'write'}
                        if path.name == 'auto-approve.yml' else {'contents': 'read'})
            self.assertEqual(workflow['permissions'], expected)
            self.assertNotIn('secrets.', path.read_text())
            for name, job in workflow['jobs'].items():
                with self.subTest(workflow=path.name, job=name):
                    self.assertEqual(job['runs-on'], 'ubuntu-24.04')
                    self.assertNotIn('repository.private', job.get('if', ''))
                    for step in job['steps']:
                        if step.get('uses', '').startswith('actions/checkout@'):
                            self.assertFalse(step['with']['persist-credentials'])
                            self.assertNotIn('token', step['with'])
                            self.assertNotIn('submodules', step['with'])

    def test_public_ci_does_not_use_privileged_pull_request_triggers(self):
        for path in (ROOT / '.github/workflows').glob('*.yml'):
            workflow = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
            self.assertNotIn('pull_request_target', workflow['on'])
            if path.name == 'auto-approve.yml':
                self.assertEqual(workflow['on'], {'workflow_run': {
                    'workflows': ['Quality gate'], 'types': ['completed']}})
                for job in workflow['jobs'].values():
                    self.assertFalse(any('checkout' in step.get('uses', '') for step in job['steps']))
            else:
                self.assertNotIn('workflow_run', workflow['on'])
                self.assertIn('pull_request', workflow['on'])

    def test_runners_do_not_mount_host_or_kubernetes_credentials(self):
        docs = list(yaml.safe_load_all((ROOT / 'deploy/github-actions-k3s/runners.yaml').read_text()))
        deployments = [doc for doc in docs if doc['kind'] == 'Deployment']
        self.assertEqual(len(deployments), 3)
        ci = [d for d in deployments if d['metadata']['name'].startswith('ha-ci-')]
        self.assertEqual(sum(d['spec']['replicas'] for d in ci), 1)
        for deployment in deployments:
            pod = deployment['spec']['template']['spec']
            self.assertFalse(pod['automountServiceAccountToken'])
            self.assertFalse(pod.get('hostNetwork', False))
            self.assertFalse(pod.get('hostPID', False))
            self.assertTrue(all('hostPath' not in volume for volume in pod['volumes']))
            self.assertEqual(pod['nodeSelector']['kubernetes.io/hostname'], 'mp')
            for container in pod['containers']:
                self.assertIn('@sha256:', container['image'])
            if deployment['metadata']['name'].startswith('ha-metadata'):
                self.assertEqual(len(pod['containers']), 1)
                self.assertTrue(pod['securityContext']['runAsNonRoot'])
                self.assertTrue(pod['containers'][0]['securityContext']['readOnlyRootFilesystem'])
                env = {item['name']: item.get('value') for item in pod['containers'][0]['env']}
                # local-path PVC roots belong to root; the runner owns this child.
                self.assertEqual(env['CONFIGURED_ACTIONS_RUNNER_FILES_DIR'], '/runner-registration/data')
            else:
                runner, docker = pod['containers']
                limits = [str(c['resources']['limits']['cpu']) for c in (runner, docker)]
                total_millicpu = sum(float(q[:-1]) if q.endswith('m') else float(q) * 1000 for q in limits)
                self.assertEqual(total_millicpu, 4000, 'The shared CI pod must retain its four-CPU ceiling')
                env = {item['name']: item.get('value') for item in runner['env']}
                for event in ('STARTED', 'COMPLETED'):
                    self.assertEqual(env['ACTIONS_RUNNER_HOOK_JOB_' + event], '/opt/runner-hooks/cleanup-docker.sh')
                self.assertIn({'name': 'runner-hooks', 'mountPath': '/opt/runner-hooks', 'readOnly': True}, runner['volumeMounts'])
                self.assertFalse(runner.get('securityContext', {}).get('privileged', False))
                self.assertEqual(docker['name'], 'docker')
                self.assertIn('--cgroup-parent="$pod_cgroup"', docker['args'][0])
                self.assertIn('cpu.max', docker['args'][0])
                volume = next(v for v in pod['volumes'] if v['name'] == 'cache')
                self.assertIn('persistentVolumeClaim', volume)
                self.assertIn({'name': 'cache', 'mountPath': '/var/lib/docker', 'subPath': 'docker'}, docker['volumeMounts'])
                for container in (runner, docker):
                    self.assertIn({'name': 'work', 'mountPath': '/runner/_work'}, container['volumeMounts'])


if __name__ == '__main__':
    unittest.main()
