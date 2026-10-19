"""Keep public CI off private runners and preserve legacy runner isolation."""
import json
from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]

# Exact reviewed expressions prevent changing trust conditions or pool roles.
CI_RUNNER = (
    "${{ fromJSON((vars.CI_RUNNER_MODE == 'self-hosted' || vars.CI_RUNNER_MODE == "
    "'k3s') && ((github.event_name == 'pull_request' && "
    'github.event.pull_request.head.repo.full_name == github.repository) || '
    '(contains(fromJSON(\'["push","schedule","workflow_dispatch"]\'), github.event_name) '
    "&& github.ref == format('refs/heads/{0}', "
    "github.event.repository.default_branch))) && (vars.CI_RUNNER_LABELS || '[]') || "
    '\'["ubuntu-latest"]\') }}'
)
AUTOMATION_RUNNER = (
    "${{ fromJSON((vars.CI_RUNNER_MODE == 'self-hosted' || vars.CI_RUNNER_MODE == "
    "'k3s') && (github.event_name == 'workflow_run' && github.ref == "
    "format('refs/heads/{0}', github.event.repository.default_branch) && "
    "github.event.workflow_run.name == 'Quality gate' && "
    "github.event.workflow_run.event == 'pull_request' && "
    "github.event.workflow_run.status == 'completed' && "
    "github.event.workflow_run.conclusion == 'success' && "
    'github.event.workflow_run.head_repository.full_name == github.repository) && '
    '(vars.CI_RUNNER_AUTOMATION_LABELS || \'[]\') || \'["ubuntu-24.04"]\') }}'
)


class RunnerBoundaryTests(unittest.TestCase):
    def test_public_jobs_preserve_scoped_runner_and_token_boundaries(self):
        permissions = {
            'ci.yml': {'contents': 'read'},
            'codeql.yml': {'contents': 'read'},
            'quality-gate.yml': {'contents': 'read'},
            'release-pipeline.yml': {'contents': 'read'},
            'release-build.yml': {'contents': 'read', 'actions': 'read'},
            'auto-approve.yml': {'contents': 'read', 'actions': 'read', 'pull-requests': 'write'},
        }
        paths = list((ROOT / '.github/workflows').glob('*.yml'))
        self.assertEqual({path.name for path in paths}, set(permissions))
        calls = {
            ('quality-gate.yml', 'check-0'): './.github/workflows/ci.yml',
            ('quality-gate.yml', 'check-1'): './.github/workflows/codeql.yml',
            ('release-pipeline.yml', 'checks'): './.github/workflows/quality-gate.yml',
            ('release-pipeline.yml', 'build'): './.github/workflows/release-build.yml',
        }
        job_permissions = {
            ('quality-gate.yml', 'check-0'): {'contents': 'read', 'actions': 'read'},
            ('quality-gate.yml', 'check-1'): {'contents': 'read', 'actions': 'read', 'security-events': 'write'},
            ('codeql.yml', 'analyze'): {'contents': 'read', 'actions': 'read', 'security-events': 'write'},
            ('release-pipeline.yml', 'checks'): {'contents': 'read', 'actions': 'read', 'security-events': 'write'},
            ('release-pipeline.yml', 'build'): {'contents': 'read', 'actions': 'read'},
            ('release-pipeline.yml', 'fuzz'): {'contents': 'read'},
        }
        for job in ('prepare', 'candidate', 'stable', 'final'):
            job_permissions[('release-pipeline.yml', job)] = {'contents': 'write', 'actions': 'read'}
        for path in paths:
            workflow = yaml.safe_load(path.read_text())
            self.assertEqual(workflow['permissions'], permissions[path.name])
            self.assertNotIn('secrets.', path.read_text())
            for name, job in workflow['jobs'].items():
                with self.subTest(workflow=path.name, job=name):
                    self.assertEqual(job.get('permissions'), job_permissions.get((path.name, name)))
                    self.assertNotIn('secrets', job)
                    if 'uses' in job:
                        self.assertNotIn('runs-on', job)
                        if name == 'fuzz':
                            policy = json.loads((ROOT / '.release-policy.json').read_text())
                            self.assertEqual(job['uses'], 'victron-venus/venus-os-ci-toolkit/.github/workflows/fuzz.yml@' + policy['fuzzing']['toolkit_ref'])
                            self.assertEqual(job['permissions'], {'contents': 'read'})
                        else:
                            self.assertEqual(job['uses'], calls[(path.name, name)])
                        continue
                    if path.name == 'codeql.yml':
                        self.assertEqual(job['runs-on'], CI_RUNNER)
                    elif path.name == 'auto-approve.yml':
                        self.assertEqual(job['runs-on'], AUTOMATION_RUNNER)
                    elif path.name == 'ci.yml':
                        self.assertEqual(job['runs-on'], 'ubuntu-24.04')
                    else:
                        runner = job['runs-on']
                        self.assertIn("|| '[\"ubuntu-latest\"]'", runner)
                        self.assertIn("github.ref == format('refs/heads/{0}', github.event.repository.default_branch)", runner)
                        self.assertIn("vars.CI_RUNNER_MODE == 'self-hosted'", runner)
                        if path.name == 'quality-gate.yml':
                            self.assertIn('github.event.pull_request.head.repo.full_name == github.repository', runner)
                        else:
                            self.assertNotIn('pull_request', runner)
                    for step in job.get('steps', []):
                        if step.get('uses', '').startswith('actions/checkout@'):
                            self.assertFalse(step['with']['persist-credentials'])
                            self.assertNotIn('token', step['with'])
                            self.assertNotIn('submodules', step['with'])

    def test_triggers_separate_validation_publication_and_metadata_only_approval(self):
        expected = {
            'ci.yml': {'workflow_call'},
            'codeql.yml': {'workflow_call'},
            'quality-gate.yml': {'pull_request', 'merge_group', 'workflow_call'},
            'release-build.yml': {'workflow_call'},
            'release-pipeline.yml': {'push', 'schedule', 'workflow_dispatch'},
            'auto-approve.yml': {'workflow_run'},
        }
        for path in (ROOT / '.github/workflows').glob('*.yml'):
            workflow = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
            self.assertEqual(set(workflow['on']), expected[path.name])
            self.assertNotIn('pull_request_target', workflow['on'])
            if path.name == 'auto-approve.yml':
                self.assertEqual(workflow['on']['workflow_run'], {'workflows': ['Quality gate'], 'types': ['completed']})
                steps = workflow['jobs']['approve']['steps']
                self.assertFalse(any('checkout' in step.get('uses', '') for step in steps))
                source = next(step['run'] for step in steps if 'run' in step)
                self.assertIn("pr['head']['sha'] == head", source)
                self.assertIn("run['conclusion'] == 'success'", source)

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
