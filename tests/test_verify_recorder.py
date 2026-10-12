"""Catch stale-but-advanced series and incomplete evidence without production I/O."""

from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'tools/verify_recorder.py'
SPEC = importlib.util.spec_from_file_location('verify_recorder', SCRIPT)
verify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify)
NOW = datetime(2026, 10, 2, 12, 10, 30, tzinfo=timezone.utc).timestamp()
CELL = 'sensor.cell'
FAULT = 'sensor.fault'
METER = 'sensor.energy'
EXCLUDED = 'sensor.alias'


def iso(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def evidence(now=NOW):
    policy = {
        'schema_version': 1,
        'entities': {
            CELL: {'runtime_kind': 'numeric', 'max_reported_age_seconds': 120,
                   'raw_required': True, 'statistics': 'measurement'},
            FAULT: {'runtime_kind': 'state', 'max_reported_age_seconds': None,
                    'raw_required': True, 'statistics': 'none'},
            METER: {'runtime_kind': 'numeric', 'max_reported_age_seconds': 3600,
                    'raw_required': True, 'statistics': 'total'},
        },
        'exclusions': {'entity_ids': [EXCLUDED], 'cutoff_ts': now - 86400},
        'retention': {'entity_ids': [CELL], 'cutoff_ts': now - 7 * 86400},
    }
    runtime = {
        'checked_at': iso(now - 1), 'config': {'state': 'RUNNING'},
        'states': [
            {'entity_id': CELL, 'state': '3.32', 'last_reported': iso(now - 1),
             'last_changed': iso(now - 86400)},
            {'entity_id': FAULT, 'state': 'off', 'last_reported': iso(now - 86400),
             'last_changed': iso(now - 86400)},
            {'entity_id': METER, 'state': '10.5', 'last_reported': iso(now - 10),
             'last_changed': iso(now - 86400)},
        ],
    }
    snapshot = {
        'collected_at_utc': iso(now - 1), 'query_errors': [],
        'database': {'server_now_ts': now - 1, 'latest_state_ts': now - 3},
        'entities': {},
        'exclusion_cutoff_ts': policy['exclusions']['cutoff_ts'],
        'purge_cutoff_ts': policy['retention']['cutoff_ts'],
    }
    for entity_id, value in ((CELL, '3.32'), (FAULT, 'off'), (METER, '10.5')):
        row = snapshot['entities'][entity_id] = {
            'latest_state': {'checked': True, 'state': value, 'last_updated_ts': now - 86400},
        }
        if entity_id == FAULT:
            continue
        for name, period in verify.STATISTICS.items():
            start = (now // period - 1) * period
            row[name] = {
                'checked': True, 'start_ts': start, 'created_ts': start + period + 10,
                'mean': 3.32, 'min': 3.3, 'max': 3.34, 'state': 10.5, 'sum': 15.0,
            }
    snapshot['entities'][CELL]['raw_states_older_than_purge_cutoff'] = {
        'checked': True, 'exists': False,
    }
    snapshot['entities'][EXCLUDED] = {
        'new_states_after_exclusion': {'checked': True, 'exists': False},
    }
    return snapshot, runtime, policy


class RecorderQualityTests(unittest.TestCase):
    def setUp(self):
        self.snapshot, self.runtime, self.policy = evidence()

    def evaluate(self, **kwargs):
        return verify.evaluate(self.snapshot, self.runtime, self.policy, now_ts=NOW, **kwargs)

    def assert_issue(self, fragment, **kwargs):
        result = self.evaluate(**kwargs)
        self.assertFalse(result['quality_passed'])
        self.assertTrue(any(fragment in item['check'] for item in result['issues']), result['issues'])
        return result

    def test_unchanged_numeric_and_static_fault_raw_can_be_healthy(self):
        # Constant numeric values and a fault that remains off need no daily raw row.
        result = self.evaluate(baseline=deepcopy(self.snapshot))
        self.assertTrue(result['quality_passed'], result['issues'])
        self.assertEqual(result['baseline_progress'][CELL]['latest_state'], 'unchanged')

    def test_settled_numeric_change_requires_raw_history_even_without_statistics(self):
        self.policy['entities'][CELL]['statistics'] = 'none'
        self.runtime['states'][0].update(state='3.70', last_changed=iso(NOW - 600))
        self.assert_issue('settled_state_change_missing_from_raw')

    def test_settled_static_fault_change_requires_raw_history(self):
        self.runtime['states'][1].update(state='on', last_changed=iso(NOW - 600))
        self.assert_issue('settled_state_change_missing_from_raw')

    def test_recent_change_can_wait_for_recorder_commit(self):
        self.runtime['states'][0].update(state='3.70', last_changed=iso(NOW - 30))
        self.assertTrue(self.evaluate()['quality_passed'])

    def test_numeric_formatting_and_restart_of_unchanged_state_are_not_lost_history(self):
        self.runtime['states'][0].update(state='3.3200', last_changed=iso(NOW - 600))
        self.runtime['states'][1]['last_changed'] = iso(NOW - 600)
        self.assertTrue(self.evaluate()['quality_passed'])

    def test_raw_newer_than_runtime_change_does_not_need_to_match_older_capture(self):
        self.runtime['states'][0].update(state='3.70', last_changed=iso(NOW - 600))
        self.snapshot['entities'][CELL]['latest_state']['last_updated_ts'] = NOW - 200
        self.assertTrue(self.evaluate()['quality_passed'])

    def test_settling_uses_both_capture_times_in_either_order_not_evaluation_time(self):
        self.runtime['states'][0].update(state='3.70', last_changed=iso(NOW - 250))
        # The change was only 50 seconds old at the earlier capture. It must
        # not become a loss merely because verification runs 200 seconds later.
        for earlier in ('database', 'runtime'):
            with self.subTest(earlier=earlier):
                self.snapshot['collected_at_utc'] = iso(NOW - (200 if earlier == 'database' else 1))
                self.runtime['checked_at'] = iso(NOW - (200 if earlier == 'runtime' else 1))
                self.assertTrue(self.evaluate()['quality_passed'])

    def test_change_after_database_capture_is_not_expected_in_that_snapshot(self):
        self.snapshot['collected_at_utc'] = iso(NOW - 200)
        self.runtime['states'][0].update(state='3.70', last_changed=iso(NOW - 150))
        self.assertTrue(self.evaluate()['quality_passed'])

    def test_missing_or_invalid_change_time_cannot_disable_raw_consistency_check(self):
        for invalid in (None, 'not-a-date', iso(NOW + 600), True):
            with self.subTest(last_changed=invalid):
                self.runtime['states'][0]['last_changed'] = invalid
                self.assert_issue('last_changed_missing_or_invalid')

    def test_raw_timestamp_clock_tolerance_avoids_false_missing_change(self):
        self.runtime['states'][0].update(state='3.70', last_changed=iso(NOW - 600))
        self.snapshot['entities'][CELL]['latest_state']['last_updated_ts'] = NOW - 615
        self.assertTrue(self.evaluate()['quality_passed'])

    def test_advanced_since_yesterday_but_stopped_series_is_not_healthy(self):
        baseline = deepcopy(self.snapshot)
        for name in verify.STATISTICS:
            baseline['entities'][CELL][name]['start_ts'] -= 86400
            self.snapshot['entities'][CELL][name]['start_ts'] -= 21600
            self.snapshot['entities'][CELL][name]['created_ts'] -= 21600
        result = self.assert_issue('stale_bucket', baseline=baseline)
        self.assertEqual(result['baseline_progress'][CELL]['latest_statistics'], 'advanced')

    def test_fresh_database_does_not_mask_unavailable_cell(self):
        self.runtime['states'][0]['state'] = 'unavailable'
        self.assert_issue('state_not_finite_numeric')

    def test_fresh_global_database_does_not_mask_stopped_cell_reports(self):
        self.runtime['states'][0]['last_reported'] = iso(NOW - 3600)
        self.assert_issue('last_reported_stale')

    def test_missing_expected_series_cannot_reduce_coverage(self):
        del self.snapshot['entities'][CELL]
        self.assert_issue('raw_unknown_or_query_error')

    def test_statistics_absent_before_and_after_is_failure_when_expected(self):
        self.snapshot['entities'][CELL]['latest_statistics'] = {'checked': True, 'no_metadata': True}
        self.assert_issue('missing_bucket', baseline=deepcopy(self.snapshot))

    def test_restored_statistics_must_exist_without_any_baseline(self):
        self.policy['entities'][CELL]['raw_after_ts'] = NOW - 60
        self.snapshot['entities'][CELL]['latest_state']['last_updated_ts'] = NOW - 5
        del self.snapshot['entities'][CELL]['latest_short_term_statistics']
        self.assert_issue('latest_short_term_statistics_unknown_or_query_error')

    def test_after_recovery_checks_creation_time_not_bucket_start(self):
        self.policy['entities'][CELL]['statistics_created_after_ts'] = NOW - 640
        # Hourly start predates recovery but creation occurs afterward: legitimate.
        self.assertTrue(self.evaluate()['quality_passed'])
        self.policy['entities'][CELL]['statistics_created_after_ts'] = NOW - 600
        self.assert_issue('not_created_after_recovery')

    def test_new_backfill_does_not_make_old_bucket_fresh(self):
        row = self.snapshot['entities'][CELL]['latest_statistics']
        row['start_ts'] -= 86400
        row['created_ts'] = NOW - 5
        self.assert_issue('stale_bucket')

    def test_hour_boundary_grace_allows_previous_completed_bucket(self):
        now = datetime(2026, 10, 2, 12, 0, 30, tzinfo=timezone.utc).timestamp()
        snapshot, runtime, policy = evidence(now)
        for entity in (CELL, METER):
            for name, period in verify.STATISTICS.items():
                row = snapshot['entities'][entity][name]
                row['start_ts'] -= period
                row['created_ts'] -= period
        self.assertTrue(verify.evaluate(snapshot, runtime, policy, now_ts=now)['quality_passed'])
        # After grace, both captures are still fresh but the old buckets fail.
        later = verify.evaluate(snapshot, runtime, policy, now_ts=now + 100)
        self.assertFalse(later['quality_passed'])
        self.assertTrue(any('stale_bucket' in item['check'] for item in later['issues']))

    def test_nan_infinity_boolean_and_missing_values_fail(self):
        for bad in ('NaN', 'Infinity', '-inf', float('nan'), True, None):
            with self.subTest(bad=bad):
                self.snapshot['entities'][CELL]['latest_statistics']['mean'] = bad
                self.assert_issue('nonfinite_or_missing_values')

    def test_meter_uses_state_and_sum_not_measurement_fields(self):
        for name in verify.STATISTICS:
            for key in ('mean', 'min', 'max'):
                del self.snapshot['entities'][METER][name][key]
        self.assertTrue(self.evaluate()['quality_passed'])
        self.snapshot['entities'][METER]['latest_statistics']['sum'] = None
        self.assert_issue('nonfinite_or_missing_values')

    def test_extrema_allow_float_roundoff_but_reject_wrong_means(self):
        row = self.snapshot['entities'][CELL]['latest_statistics']
        row.update(mean=3.3200000000000007, min=3.32, max=3.32)
        self.assertTrue(self.evaluate()['quality_passed'])
        row['mean'] = 3.4
        self.assert_issue('inconsistent_extrema')

    def test_invalid_raw_numeric_fails_even_if_live_value_recovered(self):
        self.snapshot['entities'][CELL]['latest_state']['state'] = 'unavailable'
        self.assert_issue('raw_not_finite_numeric')

    def test_static_fault_still_requires_available_current_state(self):
        self.runtime['states'][1]['state'] = 'unknown'
        self.assert_issue('state_unavailable_or_missing')

    def test_stale_and_future_snapshots_fail_even_with_fresh_series(self):
        self.runtime['checked_at'] = iso(NOW - 600)
        self.assert_issue('runtime_capture_stale')
        self.runtime['checked_at'] = iso(NOW + 600)
        self.assert_issue('runtime_capture_in_future')

    def test_naive_timestamp_cannot_inherit_local_timezone(self):
        self.runtime['checked_at'] = '2026-10-02T12:10:29'
        self.assert_issue('runtime_capture_missing_or_invalid')

    def test_query_timeout_or_missing_error_inventory_fails_closed(self):
        self.snapshot['entities'][CELL]['latest_statistics'] = {'checked': True, 'error_type': 'TimeoutError'}
        self.assert_issue('unknown_or_query_error')
        self.snapshot.pop('query_errors')
        self.assert_issue('missing_error_inventory')

    def test_wrong_purge_cutoff_cannot_reuse_an_old_success(self):
        self.snapshot['purge_cutoff_ts'] -= 86400
        self.assert_issue('retention_cutoff_mismatch')

    def test_unknown_and_found_rows_both_fail_boundary_checks(self):
        for bad in (None, True, 0, 'false'):
            with self.subTest(bad=bad):
                self.snapshot['entities'][CELL]['raw_states_older_than_purge_cutoff']['exists'] = bad
                self.assert_issue('retention_rows_present_or_unknown')

    def test_missing_exclusion_observation_fails(self):
        del self.snapshot['entities'][EXCLUDED]
        self.assert_issue('exclusions_unknown_or_query_error')

    def test_duplicate_runtime_identity_fails(self):
        self.runtime['states'].append(deepcopy(self.runtime['states'][0]))
        self.assert_issue('duplicate_entity')

    def test_unknown_cadence_or_expectation_is_invalid_policy(self):
        del self.policy['entities'][CELL]['max_reported_age_seconds']
        with self.assertRaises(ValueError):
            self.evaluate()

    def test_emits_no_values_from_input(self):
        self.runtime['states'][0]['state'] = 'credentials-must-not-be-echoed'
        self.assertNotIn('credentials-must-not-be-echoed', json.dumps(self.evaluate()))

    def test_cli_uses_exit_status_to_prevent_false_success(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = {}
            for name, payload in (('snapshot', self.snapshot), ('runtime', self.runtime), ('policy', self.policy)):
                paths[name] = Path(folder) / (name + '.json')
                paths[name].write_text(json.dumps(payload))
            command = [sys.executable, str(SCRIPT), '--now', iso(NOW)]
            for name, path in paths.items():
                command.extend(['--' + name, str(path)])
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.runtime['states'][0]['state'] = 'unavailable'
            paths['runtime'].write_text(json.dumps(self.runtime))
            failed = subprocess.run(command, capture_output=True)
            self.assertEqual(failed.returncode, 1)
            self.assertFalse(json.loads(failed.stdout)['quality_passed'])
            paths['runtime'].write_text('not-json-secret')
            invalid = subprocess.run(command, capture_output=True)
            self.assertEqual(invalid.returncode, 2)
            self.assertNotIn(b'not-json-secret', invalid.stdout + invalid.stderr)


if __name__ == '__main__':
    unittest.main()
