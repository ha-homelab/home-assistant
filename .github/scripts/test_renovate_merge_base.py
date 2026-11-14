"""Execute the vendored merger with mocked metadata; never call GitHub."""
# Narrow actual-ref regressions from Toolkit test_auto_merge.py@76f79dc0efed6766d3d975cf51b4f003ffa7c168.
import copy
import os
import re
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/toolkit-auto-merge-413248b9fdb724e787097c5c56802412a49e9467.yml"
text = WORKFLOW.read_text()
match = re.search(r"python3 (?:-I )?- <<'PY'\n", text)
assert match, "Missing embedded merger"
SOURCE = textwrap.dedent(text[match.end():].rsplit("\n          PY", 1)[0])

def own_check():
    """Represent the currently registered merger waiting on other checks."""
    return {
        "name": "Auto Merge",
        "workflowName": "Auto Merge PRs",
        "status": "IN_PROGRESS",
        "startedAt": "2026-09-12T01:23:55Z",
        "detailsUrl": "https://github.com/example/repo/actions/runs/123/job/4",
    }

def pr(author="californiantiramisu", head="abc", state="SUCCESS"):
    """Create a PR response containing a genuine independent check."""
    return {
        "state": "OPEN",
        "isDraft": False,
        "author": {"login": author},
        "baseRefName": "main",
        "baseRefOid": "base",
        "isCrossRepository": False,
        "labels": [{"name": "automerge"}],
        "headRefOid": head,
        "statusCheckRollup": [
            {"name": "CI", "status": "COMPLETED", "conclusion": state},
            own_check(),
        ],
    }

class AutoMergeTests(unittest.TestCase):
    def setUp(self):
        """Load trusted workflow definitions; API transport is mocked before main runs."""
        self.code = {"__name__": "workflow_under_test"}
        # Load repository-owned definitions; main runs only after API mocks are installed.
        # pylint: disable-next=exec-used
        exec(compile(SOURCE, str(WORKFLOW), "exec"), self.code)  # noqa: S102
        self.environment = {
            "GH_TOKEN": "test-token",
            "GITHUB_REPOSITORY": "example/repo",
            "PR_NUMBER": "7",
            "PR_AUTHORS": "4alvit,californiantiramisu",
            "MERGE_METHOD": "squash",
            "REQUIRED_CHECKS": "",
            "GITHUB_RUN_ID": "123",
            "GITHUB_ACTOR": "unrelated-event-actor",
        }

class ReviewedMergeTests(unittest.TestCase):
    def setUp(self):
        """Load the same workflow while declaring the dynamically populated namespace."""
        self.code = {}
        AutoMergeTests.setUp(self)

    @staticmethod
    def reviewed(head="abc", state="SUCCESS"):
        """Include the paginated REST review metadata used by the strict mode."""
        return pr(author="4alvit", head=head, state=state) | {
            "isCrossRepository": False,
            "reviewHistory": [
                {
                    "id": 1,
                    "user": {"login": "californiantiramisu"},
                    "state": "APPROVED",
                    "commit_id": head,
                }
            ],
        }

class SinglePassReviewedTests(unittest.TestCase):
    setUp = ReviewedMergeTests.setUp

    HEAD = "a" * 40

    BASE = "b" * 40

    @classmethod
    def ready(cls):
        """A same-repository, current-base branch with a current-head approval."""
        value = ReviewedMergeTests.reviewed(head=cls.HEAD)
        value["baseRefOid"] = cls.BASE
        value["statusCheckRollup"][1]["__typename"] = "CheckRun"
        return value

    @staticmethod
    def candidate(number=7):
        """REST candidate discovery is separate from authoritative snapshots."""
        return {
            "number": number,
            "draft": False,
            "base": {"ref": "main"},
            "head": {"repo": {"full_name": "example/repo"}},
            "user": {"login": "4alvit"},
            "labels": [{"name": "automerge"}],
        }

    def run_once(
        self,
        snapshots,
        *,
        pages=None,
        event=None,
        environment=None,
        runs=None,
        jobs=None,
        check_runs=None,
        compare=None,
        base_refs=None,
        failure=None,
        rejected_merges=(),
    ):
        """Mock only metadata transport; execute the actual main and merge decision."""
        import json  # pylint: disable=import-outside-toplevel

        current = {}
        values = (
            {number: iter(items) for number, items in snapshots.items()}
            if isinstance(snapshots, dict)
            else iter(snapshots)
        )
        branch_refs = iter(base_refs) if base_refs is not None else None

        def read_snapshot(*_args, **_kwargs):
            current.clear()
            sequence = values[int(_args[1])] if isinstance(values, dict) else values
            current.update(copy.deepcopy(next(sequence)))
            return copy.deepcopy(current)

        def transport(*args):
            if args == ("api", "user", "--jq", "{id,login,type}"):
                return json.dumps({"id": 123456, "login": "merge-account", "type": "User"})
            if args == ("api", "repos/example/repo", "--jq", ".default_branch"):
                return "main"
            if args[:2] == ("pr", "merge"):
                if int(args[2]) in rejected_merges:
                    raise self.code["subprocess"].CalledProcessError(1, args)
                return ""
            endpoint = next(item for item in args if item.startswith("repos/"))
            if failure and failure in endpoint:
                raise RuntimeError("API/authentication failed")
            if endpoint == "repos/example/repo/git/ref/heads/main":
                return next(branch_refs) if branch_refs is not None else self.BASE
            if "/actions/runs/" in endpoint:
                number = int(endpoint.rsplit("/", 1)[1])
                return json.dumps(
                    (runs or {}).get(
                        number,
                        {
                            "id": number,
                            "workflow_id": 10,
                            "repository": {"full_name": "example/repo"},
                        },
                    )
                )
            if "/actions/jobs/" in endpoint:
                number = int(endpoint.rsplit("/", 1)[1])
                return json.dumps(
                    (jobs or {}).get(
                        number,
                        {
                            "id": number,
                            "run_id": 123,
                            "name": "Auto Merge",
                            "check_run_url": "https://api.github.com/repos/example/repo/check-runs/42",
                        },
                    )
                )
            if "/check-runs?" in endpoint:
                checks = (
                    check_runs
                    if check_runs is not None
                    else [
                        {
                            "name": "Auto Merge",
                            "app": {"slug": "github-actions"},
                            "details_url": own_check()["detailsUrl"],
                            "head_sha": current["headRefOid"],
                            "url": "https://api.github.com/repos/example/repo/check-runs/42",
                        }
                    ]
                )
                return json.dumps([{"check_runs": checks}])
            if "/compare/" in endpoint:
                return compare if compare is not None else current["baseRefOid"]
            if endpoint.endswith("/pulls?state=open&per_page=100"):
                return json.dumps(pages if pages is not None else [[self.candidate()]])
            raise AssertionError(f"Unexpected API call: {args}")

        env = (
            self.environment
            | {
                "PR_NUMBER": "",
                "REVIEWED_MERGE": "true",
                "REVIEWED_SINGLE_PASS": "true",
                "REQUIRED_CHECKS": "CI",
                "GITHUB_EVENT_NAME": "workflow_run",
                "GITHUB_EVENT_PATH": "/test/event.json",
                "GITHUB_SERVER_URL": "https://github.com",
            }
            | (environment or {})
        )
        payload = (
            event
            if event is not None
            else {"repository": {"full_name": "example/repo"}}
        )
        mocked = unittest.mock.Mock(side_effect=transport)
        with (
            patch.dict(os.environ, env, clear=True),
            patch.dict(self.code, {"snapshot": read_snapshot, "gh": mocked}),
            patch(
                "builtins.open", unittest.mock.mock_open(read_data=json.dumps(payload))
            ),
            patch("time.sleep") as sleep,
        ):
            try:
                self.code["main"]()
            finally:
                self.last_calls = mocked.call_args_list
                sleep.assert_not_called()
        return mocked.call_args_list

    @staticmethod
    def merges(calls):
        """Select only actual merge mutations from read-only API calls."""
        return [call.args for call in calls if call.args[:2] == ("pr", "merge")]

    def test_default_branch_wakeups_need_no_own_check_or_pr_number(self):
        """Completion/cron events evaluate current state even for an old event head."""
        ready = self.ready()
        ready["statusCheckRollup"] = ready["statusCheckRollup"][:1]
        for event_name in ("workflow_run", "schedule", "status", "pull_request_review"):
            with self.subTest(event=event_name):
                calls = self.run_once(
                    [ready] * 3,
                    environment={"GITHUB_EVENT_NAME": event_name},
                    event={
                        "repository": {"full_name": "example/repo"},
                        "workflow_run": {"head_sha": "old", "pull_requests": []},
                    },
                )
                self.assertEqual(len(self.merges(calls)), 1)
                self.assertEqual(
                    self.merges(calls)[0][-2:], ("--match-head-commit", self.HEAD)
                )
                self.assertNotIn("--admin", self.merges(calls)[0])
                self.assertNotIn("--auto", self.merges(calls)[0])

    def test_historical_pr_base_does_not_hide_a_behind_candidate(self):
        """A green reviewed PR must include actual main, not only its old PR base."""
        behind = self.ready() | {"mergeStateStatus": "BEHIND"}
        calls = self.run_once(
            [behind] * 3,
            base_refs=["c" * 40],
            compare=self.BASE,
        )
        self.assertFalse(self.merges(calls))
        comparison = next(call for call in calls if "/compare/" in " ".join(call.args))
        self.assertIn(f"/compare/{'c' * 40}...{self.HEAD}", comparison.args[1])

    def test_behind_candidate_does_not_fail_or_starve_the_ready_candidate(self):
        """Expected outdated ancestry is skipped while a later page still merges."""
        behind = self.ready() | {"mergeStateStatus": "BEHIND"}
        ready = self.ready() | {"baseRefOid": "c" * 40}
        calls = self.run_once(
            {7: [behind] * 3, 8: [ready] * 3},
            pages=[[self.candidate()], [self.candidate(8)]],
            base_refs=["c" * 40] * 4,
            rejected_merges=(7,),
        )
        self.assertEqual([call[2] for call in self.merges(calls)], ["8"])

    def test_actual_base_advances_before_final_read_without_changing_pr_base(self):
        """Three stable PR-base values cannot mask a new default branch commit."""
        calls = self.run_once(
            [self.ready()] * 3,
            base_refs=[self.BASE, self.BASE, "c" * 40],
        )
        self.assertFalse(self.merges(calls))

    def test_unstable_own_failed_orchestration_check_does_not_block_ready_source(self):
        """Provider UNSTABLE is not a substitute for verified product-check state."""
        ready = self.ready() | {"mergeStateStatus": "UNSTABLE"}
        ready["statusCheckRollup"][1].update(status="COMPLETED", conclusion="FAILURE")
        self.assertEqual(len(self.merges(self.run_once([ready] * 3))), 1)

    def test_missing_or_malformed_actual_branch_identity_fails_closed(self):
        """A denied or incomplete branch-ref response cannot authorize a merge."""
        for value in ("", "null", "main", "c" * 39):
            with self.subTest(value=value):
                with self.assertRaisesRegex(RuntimeError, "default branch identity"):
                    self.run_once([self.ready()] * 3, base_refs=[value])
                self.assertFalse(self.merges(self.last_calls))

    def test_read_failure_aborts_before_attempting_any_candidate_merge(self):
        """Continuing after write rejection never hides a read or authentication error."""
        snapshots = [self.ready()] * 6
        pages = [[self.candidate(), self.candidate(8)]]
        with self.assertRaisesRegex(RuntimeError, "API/authentication"):
            self.run_once(snapshots, pages=pages, failure="/compare/")
        self.assertFalse(self.merges(self.last_calls))
        self.assertEqual(
            sum("/compare/" in " ".join(call.args) for call in self.last_calls), 1
        )

    def test_current_base_is_required_before_first_observation_and_merge(self):
        """A stable but outdated branch must be updated and revalidated first."""
        self.assertFalse(self.merges(self.run_once([self.ready()], compare="c" * 40)))
        calls = self.run_once([self.ready()] * 3)
        self.assertEqual(sum("/compare/" in " ".join(call.args) for call in calls), 3)

    def test_final_state_changes_never_merge(self):
        """Current base, head, decisions and eligibility are checked at the last read."""
        ready = self.ready()
        for change in (
            {"baseRefOid": "c" * 40},
            {"headRefOid": "d" * 40},
            {"reviewHistory": []},
            {"reviewHistory": [ready["reviewHistory"][0] | {"id": 2}]},
            {
                "headRefOid": "d" * 40,
                "reviewHistory": [ready["reviewHistory"][0] | {"commit_id": "d" * 40}],
            },
            {"isCrossRepository": True},
            {"state": "CLOSED"},
            {"isDraft": True},
            {"author": {"login": "stranger"}},
            {"labels": []},
            {"baseRefName": "other"},
            {"statusCheckRollup": [{"name": "CI", "status": "IN_PROGRESS"}]},
        ):
            with self.subTest(change=change):
                self.assertFalse(
                    self.merges(self.run_once([ready, ready, ready | change]))
                )

if __name__ == "__main__":
    unittest.main()
