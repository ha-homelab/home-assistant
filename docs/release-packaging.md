# Portable library releases and acceptance

The beta/RC deliverables are the `ha-notification-frame-cache` Python wheel,
source distribution and `SHA256SUMS`. They package the existing cache class,
not the household configuration. `scripts/package_cache.py` copies exactly
three tracked files into a temporary build tree: `pyproject.toml`,
`docs/notification-frame-cache.md` and
`config/housekeeping/notification_frame_cache.py`. It rejects missing or linked
inputs. No directory glob can add household configuration or operator state.

## Version and provenance

The library's initial source base is `0.1.0` in `pyproject.toml`. Child automation
and script libraries, upstream components and installation versions retain
their independent identities. The runtime module has no independent version
literal; installed distribution metadata provides its package version.

The explicit promotion profile is `promote-bytes`. Beta tag `v0.1.0-beta.7`
installs as `0.1.0b7`; RC tag `v0.1.0-rc.7` installs as `0.1.0` so later approved
stable promotion can preserve exact bytes. Keep the full tag, source SHA,
manifest and checksums to identify an RC. No stable or package-index release is
performed by this onboarding.

The allocator freezes one source- and policy-bound plan before builds. The build
downloads that plan and synchronizes only the owned metadata field. Its temporary
overlay and effective input digest are receipted; candidate versions are not
committed into the source branch. The policy inspects both wheel and source
distribution metadata. Failed allocations may leave gaps and must not be reset.

## Build and verification

Build tools are installed from the hash-locked requirements in a fresh
environment. The backend runs only in the three-file temporary source tree.
The adapter checks wheel and source-distribution inventories and then installs
each exact artifact separately in a new environment without runtime dependency
resolution. An isolated interpreter verifies the installed distribution version,
the installed module's exact source hash, synthetic-frame handling, private file
mode and cleanup using an explicitly supplied temporary directory.

Staging verifies actual wheel and source-distribution versions and writes a
receipt over both final artifacts and checksums. RC publication additionally
requires the real bounded Linux parser campaign described in [fuzzing](fuzzing.md).
Local unit or corpus replay does not establish mutation-campaign completion.

Both original configuration validation and pinned HA runtime jobs remain
required, including the existing configuration-overlay build, dependency
validators, secret scan and synthetic runtime scenarios. That existing overlay
is only a CI validation output; it is not one of this release's assets. The
opted-in maintainer auto-approval runs separately on successful Quality gate
completion, rechecks the exact current PR head and label, and executes no PR
code with its write token. Add the opt-in label before a fresh CI run.

## Reproduction and acceptance

Use a disposable checkout of the exact accepted source SHA and restore the
manifest's saved `.release-plan.json`. With Python 3.12 and `uv` available:

```sh
python3 scripts/version_plan.py sync --plan .release-plan.json
python3 scripts/package_cache.py 0.1.0 rc
python3 scripts/stage_release_assets.py --target package --pattern 'release-dist/*'
```

Use the plan's actual base and channel. Output directories must be empty.
These commands build and test local files; they do not publish or deploy.
Development builds without a plan may use consistent source metadata but cannot
receive a publication receipt. See [version plans](VERSIONING.md) and
[the release runbook](release-workflow.md) for shared lifecycle details.

Verify the chosen artifact's checksum and install it into a separate environment
as described in [the library guide](notification-frame-cache.md). Applications
must pass a private cache directory explicitly and preserve their own integration
configuration. A successful fresh installation or parser campaign does not prove
camera quality, notification delivery, HA deployment compatibility or physical
acceptance. Record the exact tag, source SHA, hashes and application results
before considering stable approval.

Any source, dependency, policy or workflow change requires a new candidate.
Never alter existing release assets or evidence. Rollback reinstalls previously
accepted immutable package bytes plus compatible application configuration; it
does not reset allocation state or run the repository's stage/promote tools.
