"""Replay the metadata-only workflow with fake API responses, never GitHub writes."""

import copy
import io
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

import yaml

ROOT = Path(__file__).resolve().parents[2]


class ApprovalBoundaryTests(unittest.TestCase):
    def setUp(self):
        workflow = yaml.safe_load(
            (ROOT / ".github/workflows/auto-approve.yml").read_text()
        )
        steps = workflow["jobs"]["approve"]["steps"]
        self.assertFalse(any("checkout" in step.get("uses", "") for step in steps))
        self.code = next(step["run"] for step in steps if "run" in step)
        self.repository = "example/consumer"
        self.run = {
            "workflow_id": 11,
            "event": "pull_request",
            "status": "completed",
            "conclusion": "success",
            "head_repository": {"full_name": self.repository},
            "head_sha": "a" * 40,
        }
        self.pr = {
            "number": 9,
            "state": "open",
            "draft": False,
            "user": {"login": "4alvit"},
            "head": {"repo": {"full_name": self.repository}, "sha": "a" * 40},
            "base": {"repo": {"full_name": self.repository}, "ref": "main"},
            "labels": [{"name": "auto-approve"}],
        }
        self.posts = []

    def execute(self):
        prefix = f"/repos/{self.repository}"
        responses = {
            prefix + "/actions/runs/7": self.run,
            prefix + "/actions/workflows/quality-gate.yml": {"id": 11},
            prefix + "/commits/" + self.run["head_sha"] + "/pulls": [{"number": 9}],
            prefix + "/pulls/9": self.pr,
        }

        def request(req, timeout):
            self.assertEqual(timeout, 30)
            if req.data is not None:
                self.posts.append((urlsplit(req.full_url).path, json.loads(req.data)))
                data = {}
            else:
                data = responses[urlsplit(req.full_url).path]
            return io.BytesIO(json.dumps(data).encode())

        with (
            patch.dict(
                os.environ,
                {
                    "GITHUB_REPOSITORY": self.repository,
                    "RUN_ID": "7",
                    "GH_TOKEN": "synthetic",
                },
            ),
            patch("urllib.request.urlopen", request),
        ):
            exec(compile(self.code, "approval-workflow", "exec"), {})  # noqa: S102 - tracked workflow, fake API only

    def test_eligible_exact_head_is_the_only_approval_target(self):
        self.execute()
        self.assertEqual(len(self.posts), 1)
        path, payload = self.posts[0]
        self.assertEqual(path, f"/repos/{self.repository}/pulls/9/reviews")
        self.assertEqual(payload["commit_id"], self.run["head_sha"])
        self.assertEqual(payload["event"], "APPROVE")

    def test_stale_fork_draft_and_missing_opt_in_do_not_write(self):
        original = copy.deepcopy(self.pr)
        for field in ("stale", "fork", "draft", "label", "author"):
            with self.subTest(field=field):
                self.pr = copy.deepcopy(original)
                if field == "stale":
                    self.pr["head"]["sha"] = "b" * 40
                elif field == "fork":
                    self.pr["head"]["repo"]["full_name"] = "example/fork"
                elif field == "draft":
                    self.pr["draft"] = True
                elif field == "label":
                    self.pr["labels"] = []
                else:
                    self.pr["user"]["login"] = "other"
                self.execute()
                self.assertEqual(self.posts, [])

    def test_unsuccessful_or_wrong_workflow_run_does_not_write(self):
        original = copy.deepcopy(self.run)
        for field, value in (
            ("conclusion", "failure"),
            ("status", "in_progress"),
            ("event", "push"),
            ("workflow_id", 12),
        ):
            with self.subTest(field=field):
                self.run = {**original, field: value}
                with self.assertRaises(SystemExit):
                    self.execute()
                self.assertEqual(self.posts, [])


if __name__ == "__main__":
    unittest.main()
