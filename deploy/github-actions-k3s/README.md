# Private HA Homelab CI on k3s

Legacy operational reference for the private repositories. This public repository
uses GitHub-hosted CI and does not include the private runner smoke workflow.
The predecessor is now named `home-assistant-private`; retain the runner group
restriction against public repositories.

The four private `ha-homelab` repositories (`home-assistant-private`, `automations`,
`scripts`, and `home-floorplan-3d`) run Linux CI on the `mp` k3s worker.
Their validation workflows explicitly select
`[self-hosted, Linux, X64, k3s, ha-homelab, private-ci]`; they never fall back
to a GitHub-hosted runner. Public repositories keep their existing routing.
Jobs reject fork PRs and public-repository execution.

One CI runner (`ha-ci-2`) is active by default, with a four-CPU ceiling.
`ha-ci-1` is a stopped reserve (`replicas: 0`). Each has a separate
Docker-in-Docker daemon so existing tests continue using the real Home Assistant image.
The daemon is privileged, but has no host paths, host Docker socket, host
network, or Kubernetes service-account token. Its workspace is shared with
its runner at the same absolute path so Docker bind mounts work correctly.
This is a trusted-private-code pool, not a sandbox for untrusted contributions.
Each CI pod requests 500m CPU / 1Gi memory in total and is limited to 4 CPU /
6Gi memory. The runner process can use 3 CPU and the Docker daemon 1 CPU.
The daemon needs its own CPU budget for cold image extraction; these operations
do not run in the nested test containers. The single active runner still bounds
total CI concurrency.
Nested Docker test containers share the pod's four-CPU ceiling rather than the
daemon-only limit. Docker explicitly places nested test containers beneath the pod's
cgroup v2 parent; startup refuses an unbounded or unexpected parent. This keeps
the aggregate CPU and memory limits effective for Docker workloads as well.
Workspaces and temporary files use bounded ephemeral storage. Each CI runner has
a separate 32Gi local-path cache PVC for Docker layers, toolchains and package
caches. These survive pod replacement; they are not shared between runners.
The local-path provisioner does not enforce a filesystem quota, so check node
disk usage and prune unused Docker images when the runner is idle.
Before and after each job, a bounded runner hook removes containers, unused
volumes and unused networks from that runner's dedicated Docker daemon. The
pre-job pass also catches containers left behind by a cancelled job or runner
crash. Docker images and local tool/package caches are retained.
Also check the physical Mac host: the dynamic 300Gi VDI is larger than its
234Gi APFS volume. Guest free space does not measure physical capacity.
Do not activate the reserve until the physical host has sufficient free disk
and CPU capacity; a second active runner also needs its own image cache.

`mp-ha-metadata-1-k3s` runs shared approval/merge workflows, selected with
`[self-hosted, Linux, X64, k3s, ha-homelab, private-metadata]`. This separate
restricted pod has no Docker daemon, runs non-root with a read-only root
filesystem, and never checks out PR source. The callers pin the shared
toolkit revision and pass explicit `runner-labels`. The metadata runner requests
100m CPU / 128Mi memory and is limited to 500m CPU / 1Gi memory.
Its runner/worker IPC startup timeout is 120 seconds so cold .NET startup does
not kill a job before its first step. Workflow deadlines remain independent.

GitHub's organization `Default` runner group must retain
`allows_public_repositories=false`. The namespaces deny ingress and private
network egress, permitting cluster DNS and public HTTPS (plus HTTP on the CI
pool). Official Ubuntu package sources use HTTPS at runner startup: their HTTP
endpoints time out on this network and otherwise delay every browser job. No Home Assistant credentials or mounts
are provided. Each runner has an independent local-path registration PVC;
restarts reuse the registration and CI caches. Losing `mp` requires re-registration on a new
node, not silently falling back to hosted CI.

## Install and operate

1. Review `runners.yaml`, verify the `k3s-heaven` kubectl context and available
   capacity on `mp`, and authenticate `gh` as an organization administrator.
2. Run `python3 deploy/github-actions-k3s/bootstrap.py` once from the repository.
   It requires PyYAML, creates Deployments at zero replicas, obtains a short-lived
   registration token through `gh`, passes it over stdin to Kubernetes, and starts
   the active CI and metadata runners. It refuses to overwrite existing namespaces or registrations.
   No account PAT is stored in the cluster or written to a file.
3. Verify the active CI and metadata names are online using
   `gh api orgs/ha-homelab/actions/runners`. Delete the temporary registration
   secrets after startup:

   ```sh
   kubectl -n github-actions-ha-ci delete secret runner-bootstrap
   kubectl -n github-actions-ha-metadata delete secret runner-bootstrap
   ```

4. Dispatch the private predecessor's `runner-smoke.yml`, then each private repository's validation workflow.
   Check the actual job `runner_name`, not merely workflow success.
5. For subsequent manifest updates, wait until the affected GitHub runners are
   idle and use `kubectl apply -f deploy/github-actions-k3s/runners.yaml`.
   Images are pinned; the Actions runner itself may auto-update through `run.sh`.
   Stop routing new work and drain jobs before scaling down or deleting a runner.
   Before first activating a reserve with an empty registration PVC, create a
   fresh short-lived `runner-bootstrap` registration-token Secret in the CI
   namespace, then scale `ha-ci-1` to one and delete the Secret after registration.
   Existing registered reserves can reuse their registration PVC.

Repository Actions variables are also configured for other shared-toolkit callers:
`CI_RUNNER_MODE=k3s`, `CI_RUNNER_LABELS` and `CI_RUNNER_RELEASE_LABELS` contain
the CI label array, and `CI_RUNNER_AUTOMATION_LABELS` contains the metadata array.
Package managers use their local caches in the runner home; setup actions do not
restore GitHub-hosted npm/pip/Go cache archives whose relative paths target a
different workspace layout. Most validation jobs allow 30 minutes for cold
toolchain and container-image setup. Floorplan browser suites run sequentially
with independent 60-minute limits; their required aggregate check covers every suite.

These are repository variables because private repositories on GitHub Free
cannot rely on organization configuration variables. Explicit workflow labels
remain authoritative even if variables are deleted.

Do not restore `ubuntu-latest` as an automatic outage fallback. A queued job
indicates a runner that needs recovery; it should not consume the hosted-minute
allowance. The manually dispatched smoke workflow is safe to rerun and makes no
changes to Home Assistant or household devices.
