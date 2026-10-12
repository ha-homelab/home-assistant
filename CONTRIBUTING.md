# Changing the running home

Use a focused branch and PR in this repository. Keep IDs stable and separate presentation edits from changed device behavior. Describe the trigger, target, conditions, timing and rollback for behavior changes.

Run the existing validators. For a metadata-only change, executable behavior must still match its baseline. For an intentional behavior change, add meaningful coverage for the changed scenario and explain the new contract before updating the baseline. Passing YAML validation alone is insufficient evidence for device operation.

Edit bundled components under `dependencies/` in the same PR and run their validators and tests as well as the root checks. Deploy an assembled immutable release and record the installed HA check and runtime verification. Protect manually disabled automations, retained MQTT messages and pending timers during reloads.

Public CI uses GitHub-hosted runners with a read-only token and no deployment credentials. Changes to this repository do not deploy the running home automatically. See `docs/public-source.md` for the publication and private runtime boundary.
