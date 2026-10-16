# Changing the running home

Use a focused branch and PR in this repository. Keep IDs stable and separate presentation edits from changed device behavior. Describe the trigger, target, conditions, timing and rollback for behavior changes.

Run the existing validators. For a metadata-only change, executable behavior must still match its baseline. For an intentional behavior change, add meaningful coverage for the changed scenario and explain the new contract before updating the baseline. Passing YAML validation alone is insufficient evidence for device operation.

Edit bundled components under `dependencies/` in the same PR and run their validators and tests as well as the root checks. Deploy an assembled immutable release and record the installed HA check and runtime verification. Protect manually disabled automations, retained MQTT messages and pending timers during reloads.

Public CI uses GitHub-hosted runners with a read-only token and no deployment credentials. Changes to this repository do not deploy the running home automatically. See `docs/public-source.md` for the publication and private runtime boundary.

## Opt-in CI approval

For an open, non-draft PR authored by `4alvit` from this repository into `main`,
a maintainer can add the `auto-approve` label to request a GitHub Actions approval.
The approval job runs only after both `validate` and `maintenance-runtime` pass.
It checks the current PR head and label again before submitting a review for that
exact commit. Remove the label to stop a pending approval; already submitted
reviews must be dismissed separately if needed.

The job handles GitHub metadata without checking out PR code and grants
`pull-requests: write` only to that job. Other jobs retain read-only permissions.
The repository's **Allow GitHub Actions to create and approve pull requests**
setting is managed in the homelab Terraform repository. Automated approval is a
maintainer opt-in to the CI gate, not an independent human review; required checks,
resolved discussions, current-branch requirements, and merge permissions still apply.

Contributions to original project code and documentation are made under the [MIT license](LICENSE). Preserve upstream copyright, license and NOTICE files for third-party material.
