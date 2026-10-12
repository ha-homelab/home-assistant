"""Verify root packages and the child delegation boundary without private repos."""

from contextlib import redirect_stdout
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
SPEC = importlib.util.spec_from_file_location("verify_release", TOOLS / "verify_release.py")
VERIFY = importlib.util.module_from_spec(SPEC)
with patch.object(sys, "path", [str(TOOLS), *sys.path]):
    SPEC.loader.exec_module(VERIFY)


def state(entity, alias, mode="single", *, identity=None, enabled="off"):
    attributes = {"friendly_name": alias, "mode": mode, "current": 0}
    if identity is not None:
        attributes["id"] = identity
    return {"entity_id": entity, "state": enabled, "attributes": attributes}


class VerifyReleaseTest(unittest.TestCase):
    def test_registry_override_requires_matching_configured_name(self):
        entity = 'script.energy'
        config = {'alias': 'Energy status report', 'mode': 'queued'}
        current = state(entity, 'Energy', 'queued')
        registry = {entity: {'name': 'Energy', 'original_name': 'Energy status report', 'platform': 'script'}}
        VERIFY.verify_metadata(entity, current, config, registry)
        with self.assertRaisesRegex(AssertionError, 'unexpected display name'):
            VERIFY.verify_metadata(entity, current, config)
        registry[entity]['original_name'] = 'Unrelated script'
        with self.assertRaisesRegex(AssertionError, 'configured name differs'):
            VERIFY.verify_metadata(entity, current, config, registry)

    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="ha-release-test-")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        packages = self.root / "config/packages"
        packages.mkdir(parents=True)
        shutil.copy(ROOT / "config/packages/igw_google_voice.yaml", packages)
        shutil.copytree(ROOT / "config/blueprints", self.root / "config/blueprints")
        self.package = {
            "automation": [
                {"id": "ha_homelab_hacs_maintenance_update", "alias": "HACS maintenance", "mode": "single"},
                {"id": "ha_homelab_hacs_maintenance_startup", "alias": "HACS startup", "mode": "restart"},
            ],
            "script": {
                "hacs_maintenance_backup": {"alias": "HACS backup", "mode": "single"},
                "hacs_maintenance_install": {"alias": "HACS install", "mode": "single"},
            },
        }
        self.write_package()
        # Root CI intentionally does not fetch either private child repository.
        # Synthetic script files exercise the real root metadata checks; the
        # automation child is a checked subprocess boundary, not reimplemented here.
        self.library_automations = [state(f"automation.library_{index}", f"Library rule {index}",
                                          identity=f"library_rule_{index}", enabled="on")
                                    for index in range(130)]
        self.before = deepcopy(self.library_automations)
        scripts = self.root / "dependencies/scripts"
        (scripts / "contracts").mkdir(parents=True)
        (scripts / "config").mkdir()
        script_config = {f"library_{index}": {"alias": f"Library script {index}", "mode": "queued"}
                         for index in range(54)}
        registry = {key: {"entity_id": f"script.{key}", "alias": config["alias"], "file": "config/library.yaml"}
                    for key, config in script_config.items()}
        (scripts / "config/library.yaml").write_text(json.dumps(script_config))
        (scripts / "contracts/script-registry.json").write_text(json.dumps({"scripts": registry}))
        self.before += [state(f"script.{key}", config["alias"], config["mode"])
                        for key, config in script_config.items()]
        self.before.append({"entity_id": "sensor.unrelated", "state": "42", "attributes": {"unit_of_measurement": "W"}})
        igw = VERIFY.read(packages / "igw_google_voice.yaml")["script"]
        self.before += [state(f"script.{key}", config["alias"], "queued") for key, config in igw.items()]
        self.current = deepcopy(self.before)
        self.current += [state(f"automation.hacs_{index}", config["alias"], config["mode"],
                               identity=config["id"], enabled="on")
                         for index, config in enumerate(self.package["automation"])]
        self.current += [state(f"script.{key}", config["alias"], config["mode"])
                         for key, config in self.package["script"].items()]

    def write_package(self):
        (self.root / "config/packages/hacs_maintenance.yaml").write_text(json.dumps(self.package))

    def verify(self, *, before=None):
        current_path = self.root / "current.json"
        before_path = self.root / "before.json"
        current_path.write_text(json.dumps(self.current))
        baseline = self.before if before is None else before
        before_path.write_text(json.dumps(baseline))
        arguments = ["verify-release", str(current_path), "--before", str(before_path), "--phase", "final"]

        def child_boundary(command, **kwargs):
            self.assertEqual(kwargs, {"check": True})
            self.assertEqual(command[:2], [sys.executable, str(self.root / "dependencies/automations/tools/verify_runtime.py")])
            self.assertEqual(command[3:6], ["--phase", "final", "--before"])
            self.assertEqual(len(command), 7)
            forwarded = json.loads(Path(command[2]).read_text())
            old = json.loads(Path(command[6]).read_text())
            package_entities = {"automation.hacs_0", "automation.hacs_1"}
            # Exact export checks prove that unknown automation/script/sensor
            # states and all original metadata still reach the child unchanged.
            self.assertEqual(forwarded, [item for item in self.current if item["entity_id"] not in package_entities])
            self.assertEqual(old, [item for item in baseline if item["entity_id"] not in package_entities])
            expected = {item["entity_id"] for item in self.library_automations}
            actual = {item["entity_id"] for item in forwarded
                      if item["entity_id"].startswith("automation.") and item["state"] in {"on", "off"}}
            if actual != expected:
                raise subprocess.CalledProcessError(1, command, stderr="Available automation set changed")
            old_enabled = {item["entity_id"]: item["state"] for item in old}
            if any(item["state"] != old_enabled[item["entity_id"]]
                   for item in forwarded if item["entity_id"] in expected):
                raise subprocess.CalledProcessError(1, command, stderr="enabled state changed")
            return subprocess.CompletedProcess(command, 0)

        with patch.object(VERIFY, "ROOT", self.root), patch.object(sys, "argv", arguments), \
                patch.object(VERIFY.subprocess, "run", side_effect=child_boundary) as child, \
                redirect_stdout(io.StringIO()) as output:
            VERIFY.main()
            child.assert_called_once()
        return output.getvalue()

    def test_declared_new_packages_pass_with_all_library_entities_and_blueprint_mode(self):
        output = self.verify()
        self.assertIn("54 folder scripts, 9 package scripts and 2 package automations", output)
        self.assertIn("2 declared script additions", output)

    def test_existing_package_entities_pass_without_claiming_additions(self):
        self.assertIn("0 declared script additions", self.verify(before=deepcopy(self.current)))

    def declare_retirement(self, key='library_0'):
        path = self.root / 'dependencies/scripts/contracts/reviewed-runtime.json'
        path.write_text(json.dumps({'retired_scripts': {key: {'date': '2026-09-22', 'reason': 'Owner retired this script'}}}))

    def test_declared_library_retirement_allows_only_that_entity_to_disappear(self):
        self.declare_retirement()
        self.current = [s for s in self.current if s['entity_id'] != 'script.library_0']
        self.assertIn('53 folder scripts', self.verify())
        self.current = [s for s in self.current if s['entity_id'] != 'script.library_1']
        with self.assertRaisesRegex(AssertionError, 'Script entity names changed'):
            self.verify()

    def test_retired_entity_must_not_remain_even_as_unavailable(self):
        self.declare_retirement()
        next(s for s in self.current if s['entity_id'] == 'script.library_0')['state'] = 'unavailable'
        with self.assertRaisesRegex(AssertionError, 'Script entity names changed'):
            self.verify()

    def test_retirement_cannot_exempt_an_unknown_entity(self):
        self.declare_retirement('unknown')
        with self.assertRaisesRegex(AssertionError, 'Unknown script retirement'):
            self.verify()

    def test_unknown_automation_reaches_child_and_its_failure_is_preserved(self):
        self.current.append(state("automation.unexpected", "Unexpected", identity="unknown", enabled="on"))
        with self.assertRaises(subprocess.CalledProcessError) as result:
            self.verify()
        self.assertIn("Available automation set changed", result.exception.stderr)

    def test_missing_library_automation_reaches_child_and_its_failure_is_preserved(self):
        self.current.pop(0)
        with self.assertRaises(subprocess.CalledProcessError) as result:
            self.verify()
        self.assertIn("Available automation set changed", result.exception.stderr)

    def test_missing_package_automation_is_rejected(self):
        self.current = [item for item in self.current if item["entity_id"] != "automation.hacs_0"]
        with self.assertRaisesRegex(AssertionError, "missing package automation ID"):
            self.verify()

    def test_changed_package_automation_identity_is_rejected(self):
        next(item for item in self.current if item["entity_id"] == "automation.hacs_0")["attributes"]["id"] = "wrong"
        with self.assertRaisesRegex(AssertionError, "missing package automation ID"):
            self.verify()

    def test_duplicate_runtime_package_identity_is_rejected(self):
        duplicate = deepcopy(next(item for item in self.current if item["entity_id"] == "automation.hacs_0"))
        duplicate["entity_id"] = "automation.impostor"
        self.current.append(duplicate)
        with self.assertRaisesRegex(AssertionError, "duplicate or missing package automation ID"):
            self.verify()

    def test_duplicate_declared_package_identity_is_rejected(self):
        path = self.root / "config/packages/duplicate.yaml"
        path.write_text(json.dumps({"automation": [self.package["automation"][0]]}))
        with self.assertRaisesRegex(AssertionError, "Duplicate package automation ID"):
            self.verify()

    def test_duplicate_runtime_entity_is_rejected_before_indexing_can_hide_it(self):
        self.current.append(deepcopy(self.current[0]))
        with self.assertRaisesRegex(AssertionError, "Duplicate runtime entity IDs"):
            self.verify()

    def test_unknown_added_script_is_rejected_even_when_unavailable(self):
        for availability in ("off", "unavailable"):
            with self.subTest(availability=availability):
                self.current.append(state("script.unknown", "Unknown", enabled=availability))
                with self.assertRaisesRegex(AssertionError, "Script entity names changed"):
                    self.verify()
                self.current.pop()

    def test_missing_library_and_package_scripts_are_rejected(self):
        library_entity = next(item["entity_id"] for item in self.before if item["entity_id"].startswith("script."))
        for entity in (library_entity, "script.igw_google_status", "script.hacs_maintenance_install"):
            with self.subTest(entity=entity):
                original = self.current
                self.current = [item for item in original if item["entity_id"] != entity]
                with self.assertRaisesRegex(AssertionError, "Script entity names changed"):
                    self.verify()
                self.current = original

    def test_package_metadata_including_blueprint_dispatcher_is_verified(self):
        for entity in ("automation.hacs_0", "script.hacs_maintenance_install", "script.igw_google_energy_dispatch"):
            item = next(item for item in self.current if item["entity_id"] == entity)
            for attribute in ("friendly_name", "mode"):
                with self.subTest(entity=entity, attribute=attribute):
                    old = item["attributes"][attribute]
                    item["attributes"][attribute] = "unexpected"
                    with self.assertRaisesRegex(AssertionError, "unexpected display name|changed execution mode"):
                        self.verify()
                    item["attributes"][attribute] = old

    def test_existing_package_automation_entity_and_enabled_state_are_preserved(self):
        baseline = deepcopy(self.current)
        item = next(item for item in self.current if item["entity_id"] == "automation.hacs_0")
        item["entity_id"] = "automation.renamed"
        with self.assertRaisesRegex(AssertionError, "package entity ID changed"):
            self.verify(before=baseline)
        item["entity_id"] = "automation.hacs_0"
        item["state"] = "off"
        with self.assertRaisesRegex(AssertionError, "enabled state changed"):
            self.verify(before=baseline)

    def test_declared_new_automation_cannot_replace_existing_identity(self):
        baseline = deepcopy(self.before)
        baseline.append(state("automation.hacs_0", "Existing rule", identity="old_identity", enabled="on"))
        with self.assertRaisesRegex(AssertionError, "existing automation registry identity changed"):
            self.verify(before=baseline)

    def test_library_enabled_state_check_is_preserved(self):
        self.current[0]["state"] = "off"
        with self.assertRaises(subprocess.CalledProcessError) as result:
            self.verify()
        self.assertIn("enabled state changed", result.exception.stderr)

    def test_library_script_metadata_check_is_preserved(self):
        item = next(item for item in self.current if item["entity_id"].startswith("script."))
        item["attributes"]["friendly_name"] = "Renamed library script"
        with self.assertRaisesRegex(AssertionError, "unexpected display name"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
