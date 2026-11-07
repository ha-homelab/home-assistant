"""Preserve the required runtime status while skipping only proven prose changes."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "runtime_change_scope", ROOT / "scripts/change_scope.py"
)
SCOPE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCOPE)
CALLER_CONDITION = (
    "${{ needs.scope.outputs.run != 'false' || "
    "needs.scope.outputs.reason != 'documentation-only' }}"
)


def workflow(name):
    return yaml.safe_load((ROOT / ".github/workflows" / name).read_text())


class MaintenanceRuntimeScope(unittest.TestCase):
    def test_required_job_and_security_validation_are_not_conditional(self):
        ci = workflow("ci.yml")
        runtime = ci["jobs"]["maintenance-runtime"]
        self.assertNotIn("if", runtime)
        self.assertNotIn("if", ci["jobs"]["validate"])
        for step in ci["jobs"]["validate"]["steps"]:
            self.assertNotIn("if", step)
        self.assertTrue(
            any(
                "gitleaks" in step.get("run", "")
                for step in ci["jobs"]["validate"]["steps"]
            )
        )
        self.assertEqual(runtime["runs-on"], "ubuntu-24.04")
        self.assertEqual(runtime["timeout-minutes"], 30)
        self.assertEqual(ci["permissions"], {"contents": "read"})

    def test_caller_and_default_require_full_runtime_without_documentation_proof(self):
        ci = workflow("ci.yml")
        self.assertEqual(set(ci["on"]), {"workflow_call"})
        control = ci["on"]["workflow_call"]["inputs"]["run-maintenance-runtime"]
        self.assertEqual(control["type"], "boolean")
        self.assertIs(control["default"], True)
        quality = workflow("quality-gate.yml")["jobs"]
        self.assertEqual(
            quality["check-0"]["with"]["run-maintenance-runtime"], CALLER_CONDITION
        )
        self.assertNotIn("if", quality["check-0"])
        self.assertNotIn("if", quality["check-1"])
        self.assertEqual(
            set(quality["check-0"]["needs"]), {"scope", "workflow-contracts"}
        )
        self.assertIn("check-0", quality["gate"]["needs"])
        self.assertTrue(
            any(
                ".github/workflow-tests" in step.get("run", "")
                for step in quality["workflow-contracts"]["steps"]
            )
        )

    def test_every_docker_scenario_uses_the_same_guard(self):
        steps = workflow("ci.yml")["jobs"]["maintenance-runtime"]["steps"]
        scenarios = [step for step in steps if "run" in step]
        self.assertEqual(len(scenarios), 28)
        for step in scenarios:
            with self.subTest(step=step["name"]):
                self.assertTrue(step["run"].startswith("docker run "))
                self.assertEqual(step["if"], "${{ inputs.run-maintenance-runtime }}")
                self.assertIn("--network none --read-only", step["run"])
                self.assertIn(
                    "ghcr.io/home-assistant/home-assistant@sha256:", step["run"]
                )
        for step in steps:
            if "uses" in step:
                self.assertNotIn("if", step)

    def test_release_push_and_explicit_qualification_stay_full(self):
        release = workflow("release-pipeline.yml")["jobs"]
        self.assertIs(release["checks"]["with"]["force-full"], True)
        classifier = next(
            step for step in release["scope"]["steps"] if step.get("id") == "scope"
        )
        self.assertEqual(classifier["env"]["FORCE_FULL"], "true")

    def test_actual_classifier_routes_documentation_and_all_unsafe_cases(self):
        policy = json.loads((ROOT / ".release-policy.json").read_text())["change_scope"]
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("GIT_")
        }
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)

            def git(*args):
                return subprocess.check_output(
                    ["git", "-C", str(repo), "-c", "core.hooksPath=/dev/null", *args],
                    env=env,
                    text=True,
                    stderr=subprocess.DEVNULL,
                ).strip()

            def commit(path, content):
                target = repo / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content)
                git("add", path)
                git(
                    "-c",
                    "user.name=CI fixture",
                    "-c",
                    "user.email=ci@example.invalid",
                    "-c",
                    "commit.gpgsign=false",
                    "commit",
                    "-m",
                    "Fixture",
                )
                return git("rev-parse", "HEAD")

            git("init", "--quiet")
            base = commit("README.md", "Initial documentation\n")
            docs = commit("docs/ordinary.md", "Ordinary guidance\n")
            source = commit("config/automation.yaml", "automation: []\n")
            semantic = commit(
                "docs/notification-frame-cache.md", "Required package metadata\n"
            )
            cases = [
                ("pull_request", base, docs, False, False),
                ("merge_group", base, docs, False, False),
                ("pull_request", docs, source, False, True),
                ("pull_request", base, source, False, True),
                ("pull_request", source, semantic, False, True),
                ("workflow_dispatch", base, docs, False, True),
                ("schedule", base, docs, False, True),
                ("push", base, docs, True, True),
                ("pull_request", base, docs, True, True),
                ("pull_request", "0" * 40, docs, False, True),
            ]
            for event_name, old, head, force, required in cases:
                event = {
                    "pull_request": {"base": {"sha": old}, "head": {"sha": head}},
                    "merge_group": {"base_sha": old, "head_sha": head},
                    "before": old,
                    "after": head,
                }
                with self.subTest(event=event_name, head=head, force=force):
                    with patch.dict(os.environ, env, clear=True):
                        result = SCOPE.classify(
                            repo,
                            event_name,
                            event,
                            policy["documentation_paths"],
                            required_paths=policy["required_paths"],
                            force=force,
                        )
                    self.assertIs(result["run"], required)
                    if not required:
                        self.assertEqual(result["reason"], "documentation-only")


if __name__ == "__main__":
    unittest.main()
