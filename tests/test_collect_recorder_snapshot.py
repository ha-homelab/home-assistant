"""Validate query boundaries and EXPLAIN guards without a database engine."""

from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


TOOLS = Path(__file__).resolve().parents[1] / "tools"
SPEC = importlib.util.spec_from_file_location("collect_recorder_snapshot", TOOLS / "collect_recorder_snapshot.py")
collector = importlib.util.module_from_spec(SPEC)
with patch.object(sys, "path", [str(TOOLS), *sys.path]):
    SPEC.loader.exec_module(collector)

CELL = "sensor.battery_cell"
INDEX = "ix_states_metadata_id_last_updated_ts"


def policy(cutoff):
    return {
        "schema_version": 1,
        "entities": {
            CELL: {"runtime_kind": "numeric", "max_reported_age_seconds": 120,
                   "raw_required": True, "statistics": "measurement"},
        },
        "exclusions": {"entity_ids": ["sensor.redundant_alias"], "cutoff_ts": cutoff},
        "retention": {"entity_ids": [CELL], "cutoff_ts": cutoff},
    }


class NormalizeBoundariesTests(unittest.TestCase):
    def test_timezone_aware_iso_and_epoch_produce_identical_numeric_parameters(self):
        expected = datetime(2026, 10, 2, 14, 30, 5, 125000, tzinfo=timezone.utc).timestamp()
        values = ("2026-10-02T14:30:05.125Z", "2026-10-02T07:30:05.125-07:00", expected)
        for value in values:
            with self.subTest(value=value):
                source = policy(value)
                original = deepcopy(source)
                result = collector.normalized_policy(source)
                for name in ("exclusions", "retention"):
                    # Binding an ISO string to numeric last_updated_ts makes
                    # MySQL compare against its year instead of the epoch.
                    self.assertIsInstance(result[name]["cutoff_ts"], (float, int))
                    self.assertEqual(result[name]["cutoff_ts"], expected)
                self.assertEqual(source, original)

    def test_invalid_cutoffs_never_reach_numeric_sql_comparisons(self):
        invalid = (None, True, False, float("nan"), float("inf"), float("-inf"),
                   "not-a-date", "2026-10-02", "2026-10-02T14:30:00", "1790951400")
        for cutoff in invalid:
            with self.subTest(cutoff=cutoff):
                with self.assertRaises(ValueError):
                    collector.normalized_policy(policy(cutoff))

    def test_invalid_boundary_scopes_are_rejected(self):
        cases = (
            {"entity_ids": [], "cutoff_ts": 1_790_950_000},
            {"entity_ids": [CELL, CELL], "cutoff_ts": 1_790_950_000},
            {"entity_ids": ["sensor.not_protected"], "cutoff_ts": 1_790_950_000},
            {"entity_ids": [CELL]},
            {"entity_ids": [CELL], "cutoff_ts": 1_790_950_000, "domain": "sensor"},
        )
        for boundary in cases:
            with self.subTest(boundary=boundary):
                source = policy(1_790_950_000)
                source["retention"] = boundary
                with self.assertRaises(ValueError):
                    collector.normalized_policy(source)


class BoundedExplainTests(unittest.TestCase):
    def test_metadata_lookups_accept_only_bounded_index_access(self):
        for access in ("ref", "range", "const", "eq_ref"):
            with self.subTest(access=access):
                self.assertTrue(collector.bounded_plan([{"key": INDEX, "type": access}], INDEX))

    def test_full_index_and_table_scans_are_rejected_even_on_expected_index(self):
        for access in ("index", "ALL", "index_merge", None, "unknown"):
            with self.subTest(access=access):
                self.assertFalse(collector.bounded_plan([{"key": INDEX, "type": access}], INDEX))

    def test_unverified_or_wrong_indexes_fail_closed(self):
        for plan in ([], [{}], [{"key": "PRIMARY", "type": "range"}],
                     [{"key": None, "type": "const"}], [{"key": INDEX}]):
            with self.subTest(plan=plan):
                self.assertFalse(collector.bounded_plan(plan, INDEX))


if __name__ == "__main__":
    unittest.main()
