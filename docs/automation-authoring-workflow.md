# Authoring automations: live debugging first, GitHub second

This runbook answers one question: after the move to YAML-mode configuration, how
does a person write or change an automation or script, prove that it works, and
get it into `ha-homelab/home-assistant` without breaking the installation.

Short answer: **develop and debug against the running installation, then capture
the proven file in Git.** Writing the rule in a pull request first and deploying
it afterwards is not the authoring loop here, because a new rule almost always
needs a live trace, a log line and at least one correction before it behaves, and
this repository cannot deploy itself. `CONTRIBUTING.md` and
[public source and private runtime](public-source.md) set that boundary: changes
become live only through a separately reviewed deployment.

## Where the files actually live

Home Assistant in this installation loads YAML-mode configuration:

```yaml
automation: !include_dir_merge_list 'automations/'
script: !include_dir_merge_named 'scripts'
```

Consequences:

- The **automation editor in the UI stays disabled** for these rules.   Home Assistant only offers the editor when `automations.yaml` is included directly.
  The `/config/automations.yaml` file exists but is not included, so editing it
  changes nothing.
- Every rule is a file on the pod. `/config/automations/<NNN>_<slug>.yaml` holds
  one rule; `/config/scripts/<folder>/<slug>.yaml` holds one script.
- The deployed tree mirrors the library in this repository, one file per rule:

| Repository | Running installation |
| --- | --- |
| `dependencies/automations/config/083_porch_turn_on_lights_after_motion.yaml` | `/config/automations/083_porch_turn_on_lights_after_motion.yaml` |
| `dependencies/scripts/config/lighting/household_lights_and_media_off.yaml` | `/config/scripts/lighting/household_lights_and_media_off.yaml` |

Entity IDs, registry metadata, helpers and integrations are **not** in this
repository. They live in the installation's `.storage` and must be changed with
supported Home Assistant APIs or the UI, then described in a document such as
[the porch lamp migration](porch-lamp-migration-2026-11-22.md).

## Step 1 — draft the rule on the live installation

Use the file that already exists when you are changing behaviour; create a new
file with the next free number when the rule is new.

```bash
# read the current rule
kubectl exec -n homeassistant home-assistant-0 -- \
  sh -c 'cat /config/automations/083_porch_turn_on_lights_after_motion.yaml'

# edit it in place (or copy an existing file as a starting point)
kubectl exec -n homeassistant home-assistant-0 -- \
  sh -c 'vi /config/automations/083_porch_turn_on_lights_after_motion.yaml'
```

Keep the existing `id` when you change behaviour. That `id` is the automation's
registry `unique_id`; changing it creates a second registry entry and can leave a
suffixed `entity_id` behind. New rules get a new `id` in the same
`ha_homelab_<slug>` style and an English `alias`, a `description`, and an explicit
`mode`.

## Step 2 — reload and debug while it is live

Before any reload, confirm that no automation action is running, because a reload
re-attaches triggers and resets pending `for` timers:

```bash
hass-cli -o json raw get /api/states > /private/path/before-reload-states.json
python tools/verify_idle.py /private/path/before-reload-states.json
hass-cli --timeout 60 service call automation.reload
```

Then exercise the rule and read what happened:

- Traces: Settings → Automations → open the rule → **Traces** (five are retained
  per automation). A trace shows which trigger fired, which condition stopped the
  run, and the exact template output.
- Logs: `kubectl logs -n homeassistant home-assistant-0 --since=15m | grep -i <slug>`.
- States: `GET /api/states/<entity_id>` before and after, not just the UI badge.
- Manual runs are allowed for logic that is safe to repeat. Do not fire lighting,
  water, heat or energy actions just to see them work when a natural event or a
  guarded test call can answer the question.

Iterate on the live file until the behaviour is right. This loop is the reason
the repository is not the first place a rule is written.

## Step 3 — capture the proven file in the repository

```bash
git -C ~/victron/home-assistant-public switch -c automation/<slug>-$(date +%Y%m%d)
kubectl exec -n homeassistant home-assistant-0 -- \
  sh -c 'cat /config/automations/083_porch_turn_on_lights_after_motion.yaml' \
  > ~/victron/home-assistant-public/dependencies/automations/config/083_porch_turn_on_lights_after_motion.yaml
```

Then in the repository:

1. Keep the live file's behaviour byte-for-byte. Formatting-only normalisation is
   fine; changing a trigger, condition, action, delay or mode while copying is
   not, because the copy is supposed to be evidence of what ran.
2. Register the file in `dependencies/automations/migration/automations.json`
   when it is new or changed identity (see below).
3. Update the affected contract files under
   `dependencies/scripts/contracts/` when a script's entity references or action
   structure changed; the scripts validator reports what no longer matches.
4. Run the source checks:

```bash
python tools/validate.py
python dependencies/automations/tools/validate.py
python dependencies/scripts/tools/validate.py
```

Passing YAML validation is not proof that a device acts. The trace and state
evidence from Step 2 is the operational proof; the validators only prove the
source contract.

## Step 4 — the migration inventory, and what "new automation" costs

`dependencies/automations/migration/automations.json` is an inventory contract,
not a convenience list: 97 active rules plus 33 retired ones account for the
original 130-rule import. `validate_inventory()` in
`dependencies/automations/tools/config_contract.py` asserts that the include order
matches the manifest, that `automation_count` equals the active entries, and that
orders are exactly `1..130`.

A genuinely new rule therefore fails the validator by design. That is a gate, not
a bug: extending the inventory means a deliberate, reviewed change to
`automation_count`, to the `range(1, 131)` expectation and to the manifest entry,
in the same pull request that adds the rule. Retiring a rule is cheaper: move its
entry to `retired_automations` with a `retirement.date` and
`retirement.reason` and delete the file. Prefer extending an existing rule over
adding a parallel one when the trigger and guards are the same.

## Step 5 — pull request

- One focused branch per rule or per coherent group, per `CONTRIBUTING.md`.
- Describe the trigger, target, guards, timing and rollback in the PR body.
- Say what the live trace proved and what was not exercised, for example "motion
  trace confirmed the light command; the notification target was not delivered
  to a phone".
- Keep IDs immutable and keep presentation changes separate from behaviour
  changes.
- Public CI runs on hosted runners with a read-only token and cannot deploy.

```bash
git -C ~/victron/home-assistant-public add dependencies/automations/config/083_porch_turn_on_lights_after_motion.yaml \
  dependencies/automations/migration/automations.json docs/
git -C ~/victron/home-assistant-public commit -m "Update porch motion rule after live verification"
git -C ~/victron/home-assistant-public push -u origin HEAD
gh pr create --repo ha-homelab/home-assistant --fill
```

## Step 6 — deploy the reviewed commit

Deployment is the separately reviewed step in
[deployment.md](deployment.md): build an immutable release, stage it against the
installed configuration, promote it, then reload and verify states. Automation-only
changes use `--scope automations`; changes that also touch the script library or
root files use `--scope overlay`. Keep the receipt private.

After the reload, re-read the affected states and check the log for new errors.
Because the live file was already correct, a diff between the promoted file and
the file you debugged should be empty — if it is not, stop and find out why the
deployment did not carry your change.

## Rollback

Before promotion, `tools/promote.py` restores the previous files automatically.
After a reload with new identities registered, do not restore the old ID-less
files: build and stage the seed again as described in deployment.md, or restore the
previous file content while keeping the registered `id`. Registry records
(`.storage/core.entity_registry`, `.storage/core.config_entries`) are not edited by
hand; change them through the API or the UI.

## Worked example: an entity rename ripples into YAML

[Porch lamp migration — 2026-11-22](porch-lamp-migration-2026-11-22.md) shows the
full order of operations: rename the registry entity first, remove the stale
helper member and voice aliases through supported APIs, then find every YAML
reference to the old entity ID with a repository-wide search and decide, per
rule, whether to retire it or re-point it. The YAML edit comes last, because an
automation that references an entity which no longer exists reloads cleanly and
silently does nothing.
