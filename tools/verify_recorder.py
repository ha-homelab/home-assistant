#!/usr/bin/env python3
"""Evaluate exported Recorder evidence without a database or network connection.

The policy names the expected entities and statistics; absence cannot silently
reduce coverage. Progress since a baseline is evidence, never a health check.
Timestamps are UTC epochs or timezone-aware ISO strings. See evaluate() for the
snapshot contract; all input files remain local and raw values are not emitted.
"""

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path


DEFAULT_LIMITS = {
    'snapshot_max_age_seconds': 300,
    'clock_skew_seconds': 30,
    'recorder_max_age_seconds': 120,
    'statistics_grace_seconds': 120,
    'raw_change_grace_seconds': 120,
}
STATISTICS = {
    'latest_short_term_statistics': 300,
    'latest_statistics': 3600,
}
UNAVAILABLE = {'unknown', 'unavailable', '', 'none'}


def finite_number(value):
    """Reject bool, null, NaN and infinities, including their JSON strings."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def timestamp(value):
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return None
        return parsed.timestamp()
    return finite_number(value)


def validate_policy(policy):
    if (not isinstance(policy, dict) or type(policy.get('schema_version')) is not int
            or policy['schema_version'] != 1):
        raise ValueError('Unsupported policy schema')
    entities = policy.get('entities')
    if not isinstance(entities, dict) or not entities:
        raise ValueError('Policy must name at least one protected entity')
    limits = dict(DEFAULT_LIMITS)
    supplied = policy.get('limits', {})
    if not isinstance(supplied, dict) or set(supplied) - limits.keys():
        raise ValueError('Unknown policy limit')
    limits.update(supplied)
    for key, value in limits.items():
        number = finite_number(value)
        if number is None or number < 0 or (key != 'clock_skew_seconds' and number == 0):
            raise ValueError('Policy limits must be finite nonnegative durations')
        limits[key] = number
    for entity_id, rule in entities.items():
        if not isinstance(entity_id, str) or '.' not in entity_id or not isinstance(rule, dict):
            raise ValueError('Invalid protected entity policy')
        allowed = {
            'runtime_kind', 'max_reported_age_seconds', 'raw_required',
            'raw_after_ts', 'statistics', 'statistics_created_after_ts',
        }
        if set(rule) - allowed:
            raise ValueError('Unknown protected entity policy field')
        if rule.get('runtime_kind') not in {'numeric', 'state'}:
            raise ValueError('Entity runtime_kind must be explicit')
        if rule.get('statistics') not in {'measurement', 'total', 'none'}:
            raise ValueError('Entity statistics expectation must be explicit')
        if not isinstance(rule.get('raw_required'), bool):
            raise ValueError('Entity raw_required must be explicit')
        if 'max_reported_age_seconds' not in rule:
            raise ValueError('Reporting cadence must be explicit; null permits static states')
        cadence = rule['max_reported_age_seconds']
        if cadence is not None and (finite_number(cadence) is None or float(cadence) <= 0):
            raise ValueError('Invalid reporting cadence')
        for field in ('raw_after_ts', 'statistics_created_after_ts'):
            if field in rule and timestamp(rule[field]) is None:
                raise ValueError('Invalid activation or recovery cutoff')
    for name in ('exclusions', 'retention'):
        if name not in policy:
            continue
        rule = policy[name]
        if not isinstance(rule, dict) or set(rule) != {'entity_ids', 'cutoff_ts'}:
            raise ValueError('Boundary checks require entity_ids and cutoff_ts')
        ids = rule['entity_ids']
        if (not isinstance(ids, list) or not ids
                or not all(isinstance(item, str) and '.' in item for item in ids)
                or len(ids) != len(set(ids)) or timestamp(rule['cutoff_ts']) is None):
            raise ValueError('Invalid boundary check scope or cutoff')
        if name == 'retention' and any(
            item not in entities or not entities[item]['raw_required'] for item in ids
        ):
            raise ValueError('Retention entities must also have protected raw history')
        if name == 'exclusions' and set(ids) & entities.keys():
            raise ValueError('An entity cannot be both excluded and protected')
    return limits


def evaluate(snapshot, runtime, policy, *, now_ts=None, baseline=None):
    """Check fresh, complete DB and runtime snapshots against explicit expectations.

    DB: collected_at_utc; query_errors (list); database.server_now_ts and
    latest_state_ts; entities[id].latest_state {checked,state,last_updated_ts};
    latest_statistics/latest_short_term_statistics {checked,start_ts,created_ts,
    mean,min,max,state,sum}. Runtime: checked_at (or collected_at_utc),
    config.state='RUNNING', states=[HA state objects including last_changed and
    last_reported].
    Boundary checks use the original verifier's checked/exists rows and cutoffs.
    """
    limits = validate_policy(policy)
    if not isinstance(snapshot, dict) or not isinstance(runtime, dict):
        raise ValueError('Snapshots must be JSON objects')
    now = datetime.now(timezone.utc).timestamp() if now_ts is None else timestamp(now_ts)
    if now is None:
        raise ValueError('Evaluation time must be a valid timestamp')
    result = {
        'schema_version': 1, 'evaluated_at_utc': datetime.fromtimestamp(now, timezone.utc).isoformat(),
        'quality_passed': False, 'limits': limits, 'issues': [], 'entities': {},
        'checks': {}, 'baseline_progress': {},
        'limits_of_evidence': [
            'Fresh last_reported proves HA received an update; it does not prove the upstream physical sample changed.',
            'A fresh aggregate proves the bucket exists, not that every sample or transient within it was retained.',
            'Cutoff checks prove a fixed boundary; they do not prove that a scheduled purge ran.',
        ],
    }

    def issue(scope, check, entity_id=None):
        row = {'scope': scope, 'check': check}
        if entity_id is not None:
            row['entity_id'] = entity_id
        result['issues'].append(row)

    def fresh(value, max_age, scope, check, entity_id=None):
        parsed = timestamp(value)
        if parsed is None:
            issue(scope, check + '_missing_or_invalid', entity_id)
        elif parsed > now + limits['clock_skew_seconds']:
            issue(scope, check + '_in_future', entity_id)
        elif now - parsed > max_age:
            issue(scope, check + '_stale', entity_id)
        return parsed

    def checked(row, check, entity_id):
        if not isinstance(row, dict) or row.get('checked') is not True or 'error_type' in row:
            issue('database', check + '_unknown_or_query_error', entity_id)
            return False
        return True

    database_capture = fresh(snapshot.get('collected_at_utc'), limits['snapshot_max_age_seconds'], 'snapshot', 'database_capture')
    runtime_capture = fresh(runtime.get('checked_at', runtime.get('collected_at_utc')), limits['snapshot_max_age_seconds'], 'snapshot', 'runtime_capture')
    errors = snapshot.get('query_errors')
    if not isinstance(errors, list) or errors:
        issue('database', 'query_errors_or_missing_error_inventory')
    database = snapshot.get('database', {})
    if not isinstance(database, dict):
        database = {}
    fresh(database.get('server_now_ts'), limits['snapshot_max_age_seconds'], 'database', 'server_clock')
    fresh(database.get('latest_state_ts'), limits['recorder_max_age_seconds'], 'database', 'global_recorder')
    config = runtime.get('config', {})
    if not isinstance(config, dict) or config.get('state') != 'RUNNING':
        issue('runtime', 'core_not_running_or_unknown')
    runtime_states = {}
    states = runtime.get('states')
    if not isinstance(states, list):
        issue('runtime', 'states_missing_or_invalid')
        states = []
    for state in states:
        if not isinstance(state, dict) or not isinstance(state.get('entity_id'), str):
            issue('runtime', 'invalid_state_record')
            continue
        entity_id = state['entity_id']
        if entity_id in runtime_states:
            issue('runtime', 'duplicate_entity', entity_id)
        runtime_states[entity_id] = state
    rows = snapshot.get('entities', {})
    if not isinstance(rows, dict):
        rows = {}

    for entity_id, rule in policy['entities'].items():
        start_issues = len(result['issues'])
        state = runtime_states.get(entity_id, {})
        value = state.get('state')
        if rule['runtime_kind'] == 'numeric':
            if finite_number(value) is None:
                issue('runtime', 'state_not_finite_numeric', entity_id)
        elif not isinstance(value, str) or value.lower() in UNAVAILABLE:
            issue('runtime', 'state_unavailable_or_missing', entity_id)
        cadence = rule['max_reported_age_seconds']
        if cadence is not None:
            fresh(state.get('last_reported'), float(cadence), 'runtime', 'last_reported', entity_id)
        row = rows.get(entity_id, {})
        if not isinstance(row, dict):
            row = {}
        if rule['raw_required']:
            raw = row.get('latest_state')
            if checked(raw, 'raw', entity_id):
                raw_ts = timestamp(raw.get('last_updated_ts'))
                # Unchanged measurements and static faults need no new raw row.
                if raw_ts is None or raw_ts > now + limits['clock_skew_seconds']:
                    issue('database', 'raw_timestamp_missing_or_invalid', entity_id)
                cutoff = timestamp(rule.get('raw_after_ts'))
                if cutoff is not None and (raw_ts is None or raw_ts < cutoff):
                    issue('database', 'raw_not_recorded_after_activation', entity_id)
                raw_value = raw.get('state')
                if rule['runtime_kind'] == 'numeric':
                    if finite_number(raw_value) is None:
                        issue('database', 'raw_not_finite_numeric', entity_id)
                elif not isinstance(raw_value, str) or raw_value.lower() in UNAVAILABLE:
                    issue('database', 'raw_unavailable_or_missing', entity_id)
                changed = timestamp(state.get('last_changed'))
                if changed is None or changed > now + limits['clock_skew_seconds']:
                    issue('runtime', 'last_changed_missing_or_invalid', entity_id)
                elif (raw_ts is not None and database_capture is not None
                      and runtime_capture is not None
                      and changed <= min(database_capture, runtime_capture)
                          - limits['raw_change_grace_seconds']
                      and raw_ts < changed - limits['clock_skew_seconds']):
                    # Either capture may precede the other. Only a change that
                    # had settled before BOTH captures must be represented in
                    # raw history. Old unchanged rows remain valid, including
                    # a restart that reports the same value with a new time.
                    if rule['runtime_kind'] == 'numeric':
                        live_number, raw_number = finite_number(value), finite_number(raw_value)
                        differs = (live_number is not None and raw_number is not None
                                   and live_number != raw_number)
                    else:
                        differs = isinstance(value, str) and isinstance(raw_value, str) and value != raw_value
                    if differs:
                        issue('database', 'settled_state_change_missing_from_raw', entity_id)
        if rule['statistics'] != 'none':
            for name, period in STATISTICS.items():
                stat = row.get(name)
                if not checked(stat, name, entity_id):
                    continue
                earliest = math.floor((now - limits['statistics_grace_seconds']) / period) * period - period
                latest = math.floor((now + limits['clock_skew_seconds']) / period) * period - period
                start = timestamp(stat.get('start_ts'))
                created = timestamp(stat.get('created_ts'))
                if start is None:
                    issue('database', name + '_missing_bucket', entity_id)
                elif start < earliest:
                    issue('database', name + '_stale_bucket', entity_id)
                elif start > latest or start % period != 0:
                    issue('database', name + '_invalid_bucket', entity_id)
                if (created is None or created > now + limits['clock_skew_seconds']
                        or (start is not None and created < start + period - limits['clock_skew_seconds'])):
                    issue('database', name + '_invalid_creation_time', entity_id)
                recovery = timestamp(rule.get('statistics_created_after_ts'))
                if recovery is not None and (created is None or created < recovery):
                    issue('database', name + '_not_created_after_recovery', entity_id)
                fields = ('mean', 'min', 'max') if rule['statistics'] == 'measurement' else ('state', 'sum')
                values = [finite_number(stat.get(field)) for field in fields]
                if any(value is None for value in values):
                    issue('database', name + '_nonfinite_or_missing_values', entity_id)
                elif rule['statistics'] == 'measurement':
                    mean, minimum, maximum = values
                    # Time-weighted float arithmetic can differ by a few ulps
                    # from a constant sample; do not report that as bad data.
                    below = mean < minimum and not math.isclose(mean, minimum, rel_tol=1e-9, abs_tol=1e-12)
                    above = mean > maximum and not math.isclose(mean, maximum, rel_tol=1e-9, abs_tol=1e-12)
                    if minimum > maximum or below or above:
                        issue('database', name + '_inconsistent_extrema', entity_id)
        result['entities'][entity_id] = {'passed': len(result['issues']) == start_issues}

    for block, field, cutoff_field in (
        ('exclusions', 'new_states_after_exclusion', 'exclusion_cutoff_ts'),
        ('retention', 'raw_states_older_than_purge_cutoff', 'purge_cutoff_ts'),
    ):
        if block not in policy:
            continue
        rule = policy[block]
        if timestamp(snapshot.get(cutoff_field)) != timestamp(rule['cutoff_ts']):
            issue('policy', block + '_cutoff_mismatch_or_missing')
        passed = 0
        for entity_id in rule['entity_ids']:
            row = rows.get(entity_id, {})
            check = row.get(field) if isinstance(row, dict) else None
            if not checked(check, block, entity_id):
                continue
            if check.get('exists') is not False:
                issue('policy', block + '_rows_present_or_unknown', entity_id)
            else:
                passed += 1
        result['checks'][block] = {'passed': passed, 'expected': len(rule['entity_ids'])}

    if baseline is not None:
        previous = baseline.get('entities', {}) if isinstance(baseline, dict) else {}
        for entity_id in policy['entities']:
            evidence = result['baseline_progress'][entity_id] = {}
            for field, stamp in [('latest_state', 'last_updated_ts'), *[(name, 'start_ts') for name in STATISTICS]]:
                old = previous.get(entity_id, {}).get(field, {})
                new = rows.get(entity_id, {}).get(field, {})
                a, b = timestamp(old.get(stamp)), timestamp(new.get(stamp))
                evidence[field] = ('unknown' if a is None or b is None else
                                   'advanced' if b > a else 'unchanged' if a == b else 'backwards')
    result['quality_passed'] = not result['issues']
    result['checks']['protected_entities'] = {
        'passed': sum(row['passed'] for row in result['entities'].values()),
        'expected': len(policy['entities']),
    }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('snapshot', 'runtime', 'policy'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--now', help='Explicit UTC evaluation time for historical replay')
    args = parser.parse_args()
    try:
        result = evaluate(
            json.loads(args.snapshot.read_text()), json.loads(args.runtime.read_text()),
            json.loads(args.policy.read_text()), now_ts=args.now,
            baseline=json.loads(args.baseline.read_text()) if args.baseline else None,
        )
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
        # Do not echo malformed input or exceptions that may contain credentials.
        print(json.dumps({'quality_passed': False, 'error': 'invalid_input'}))
        return 2
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if result['quality_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
