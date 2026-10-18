# Public source and private runtime

For the illustrated workflow and evidence limits, see the [visual guide](process-and-evidence.md).

This repository starts with a fresh source snapshot. Earlier Git history, pull
requests, workflow logs and deployment records remain in the private predecessor;
they are not imported into this repository. Historical runbooks describe earlier
installations and may reference private infrastructure or unavailable commits.

## One source tree

`dependencies/automations` and `dependencies/scripts` are ordinary tracked
directories, not submodules. Clone this repository over HTTPS, install
`requirements.txt`, and run:

```sh
python tools/validate.py
python dependencies/automations/tools/validate.py
python dependencies/scripts/tools/validate.py
python -m unittest discover -s tests -p test_build.py -v
python tools/build.py /tmp/ha-release
```

Run each component's tests from its own directory. Runtime tests require the
Home Assistant environment documented in `.github/workflows/ci.yml`.

The release builder copies only tracked configuration files. It rejects dirty
trees, symlinks and nested repositories. `release.json` records the root commit;
`components` contains Git **tree** hashes with
`component_revision_type: git-tree`, not separate repository commit IDs. Keep
these receipts private when adding runtime-specific verification data.

## Deployment values

Only secret names and example values belong in Git. Supply the installation's
`secrets.yaml` explicitly to the builder with `--secrets`; never copy a live HA
configuration directory, `.storage`, database, camera image or backup into this
repository. Existing custom integrations and storage-managed entities remain
installation prerequisites; this is a configuration overlay, not a complete
backup or a turnkey new installation.

`home_assistant_external_url` supplies the root configuration, camera paths and
`input_text.base_url`. The TV snapshot script reads that existing helper.
Historical URL samples in `dependencies/scripts/contracts/source-baseline.json`
use `ha.example.invalid`; their entity IDs and action structure are retained.
The reviewed runtime contract records the TV script's configurable URL.
Camera hardware/address-to-room inventories are deliberately excluded.

## CI and deployment boundary

Public pull requests run on GitHub-hosted Ubuntu runners with a read-only
`GITHUB_TOKEN`. CI has no `BOT_PAT`, private submodule access, HA token, SSH key,
home-network runner or deployment step. Keep CI_RUNNER_MODE and all CI_RUNNER_*_LABELS variables unset for this public repository; the generated orchestration must use its hosted fallback. Home Assistant runtime tests mock device
services and run in containers with networking disabled.

The legacy private runner manifests under `deploy/github-actions-k3s` are
reference material for trusted private repositories. Do not register those
runners with this public repository or enable public-repository access for the
private runner group.

Changes become live only through a separately reviewed deployment using the
existing private infrastructure. A source publication does not reload HA,
change device state, or replace its stored configuration.

## History boundary

Create publication snapshots from tracked files in a new directory and initialize
a new Git repository. Do not mirror-push the predecessor, copy its `.git`
directory, import its branches or tags, or use it as a fork origin. Point old
working copies at the private predecessor before reusing the original name.

Future contributions belong in a fresh clone of this repository. Keep secret
scanning and push protection enabled and run the source scanner in CI.

The versioned library release workflow has narrowly scoped contents-write jobs
for allocation and publication. Validation and package building retain read-only
tokens. The opt-in approval workflow uses only PR metadata after a successful
Quality gate and never checks out or executes PR code with its write token.
Neither workflow receives deployment or private-runner credentials.
