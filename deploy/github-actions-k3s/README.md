# Dedicated CI runner reference

This public repository uses GitHub-hosted validation as declared in
[the pinned CI workflow](https://github.com/ha-homelab/home-assistant/blob/b10fa9a87a356f8942aef383042c6a23e6cebcbd/.github/workflows/ci.yml).
The manifests and bootstrap helper in this directory are an operational reference
for a separately administered trusted runner pool. They are not required to build,
test or deploy the Home Assistant configuration.

## Trust and isolation

Keep a trusted runner group restricted to explicitly approved repositories.
Do not enable public-repository access or route untrusted fork pull requests to a
pool that has access to installation resources. A separate metadata runner can
handle approval and merge automation without checking out pull-request source.
These restrictions must remain in both repository workflow conditions and runner
group settings; changing repository visibility does not make a private pool safe.

A Docker-in-Docker worker needs a dedicated daemon and bounded CPU, memory,
ephemeral storage and image-cache capacity. Do not mount the host Docker socket,
host paths or cluster credentials into jobs. Constrain nested containers with the
worker's aggregate cgroup limit; daemon-only limits do not bound child workloads.
Clean abandoned containers, networks and volumes between jobs while retaining only
reviewed tool and image caches. A local-path volume declaration is not a filesystem
quota, and guest free space is not the same as physical host free space.

## Installation and maintenance

Treat the checked-in manifests as reference inputs. Before any installation,
review the organization, runner group, labels, node selectors, resource limits,
storage class, namespaces and network policy against a separately maintained
operator inventory. Never use a repository document as proof of current cluster
state or available capacity.

The bootstrap helper has side effects: it creates cluster resources, requests
short-lived runner registration credentials and starts the selected workers.
Use it only after explicit operator review of the target kubeconfig and rendered
resources. Do not execute it as part of ordinary application CI. Registration
credentials must stay out of Git and logs, and temporary bootstrap credentials
must be removed after successful registration.

Before changing manifests, stop routing new work to the affected workers and wait
until their jobs are idle. Verify an actual job's runner identity after a routing
change. Activating a reserve requires independent capacity, storage and registration
checks; do not interpret a queued job as permission to expand a pool or change its
trust boundary. Maintain installation names, exact capacity, recovery commands and
repo assignments in the operator inventory, outside this public documentation.
