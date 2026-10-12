#!/usr/bin/env python3
"""Collect bounded Recorder evidence in the installed HA container, without writes.

Credentials are resolved from the active YAML inside the container. The output
contains only explicitly selected entity values/aggregate fields, never URLs,
credentials or arbitrary state attributes. Treat the snapshot as private data.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

from verify_recorder import timestamp, validate_policy


def normalized_policy(policy):
    """Never let MySQL coerce an ISO date string to a numeric year."""
    validate_policy(policy)
    result = dict(policy)
    for name in ("exclusions", "retention"):
        if name in policy:
            result[name] = {**policy[name], "cutoff_ts": timestamp(policy[name]["cutoff_ts"])}
    return result


def bounded_plan(plan, index):
    """A full index scan is not a bounded metadata lookup, even with LIMIT 1."""
    return any(row.get("key") == index and row.get("type") in
               ("ref", "range", "const", "eq_ref") for row in plan)


def collect(policy, config_root="/config"):
    """Use indexed LIMIT 1 lookups; no COUNT, table scans or maintenance calls."""
    import yaml
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import NullPool

    policy = normalized_policy(policy)
    expected = policy.get("entities", {})
    exclusions = policy.get("exclusions", {})
    retention = policy.get("retention", {})
    entity_ids = sorted(set(expected) | set(exclusions.get("entity_ids", []))
                        | set(retention.get("entity_ids", [])))
    if not entity_ids or len(entity_ids) > 500:
        raise ValueError("Expected between 1 and 500 explicitly selected entities")
    root = Path(config_root)

    def mapping(path):
        return {key.value: value for key, value in yaml.compose(path.read_text()).value}

    recorder = mapping(root / "configuration.yaml")["recorder"]
    configuration = (mapping(root / recorder.value) if recorder.tag == "!include"
                     else {key.value: value for key, value in recorder.value})
    url = configuration["db_url"]
    db_url = mapping(root / "secrets.yaml")[url.value].value if url.tag == "!secret" else url.value
    engine = create_engine(db_url, poolclass=NullPool, connect_args={"connect_timeout": 10})
    output = {
        "schema_version": 1, "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "database": {}, "entities": {}, "query_errors": [], "query_count": 0,
        "query_seconds": 0, "verified_index_plans": {},
        "exclusion_cutoff_ts": exclusions.get("cutoff_ts"),
        "purge_cutoff_ts": retention.get("cutoff_ts"),
    }
    state_index = "ix_states_metadata_id_last_updated_ts"
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            # This transient per-connection setting is the sole non-SELECT statement.
            connection.execute(text("SET SESSION MAX_EXECUTION_TIME=3000"))

            def query(name, sql, parameters=None, index=None):
                started = time.monotonic()
                try:
                    if index and name not in output["verified_index_plans"]:
                        plan = [dict(row._mapping) for row in connection.execute(
                            text("EXPLAIN FORMAT=TRADITIONAL " + sql), parameters or {})]
                        if not bounded_plan(plan, index):
                            raise ValueError("Expected bounded index plan was not selected")
                        output["verified_index_plans"][name] = plan
                    return [dict(row._mapping) for row in connection.execute(text(sql), parameters or {})]
                except Exception as error:
                    # Do not emit driver exceptions: they can contain credentials/SQL.
                    issue = {"query": name, "error_type": type(error).__name__}
                    output["query_errors"].append(issue)
                    return issue
                finally:
                    output["query_count"] += 1
                    output["query_seconds"] += time.monotonic() - started

            def one(name, sql, parameters=None, index=None):
                result = query(name, sql, parameters, index)
                return {"checked": True, **(result if isinstance(result, dict) else result[0] if result else {})}

            clock = one("server_time", "SELECT UNIX_TIMESTAMP() AS now_ts")
            latest = one("global_latest_state", "SELECT state_id,last_updated_ts FROM states ORDER BY state_id DESC LIMIT 1")
            now, last = clock.get("now_ts"), latest.get("last_updated_ts")
            age = now - last if now is not None and last is not None else None
            output["database"] = {
                "server_now_ts": now, "latest_state_id": latest.get("state_id"),
                "latest_state_ts": last, "state_age_seconds": age,
                "recorder_fresh": -30 <= age <= 120 if age is not None else None,
            }
            placeholders = ",".join(":e" + str(i) for i in range(len(entity_ids)))
            parameters = {"e" + str(i): entity for i, entity in enumerate(entity_ids)}
            state_rows = query("state_metadata", "SELECT metadata_id,entity_id FROM states_meta WHERE entity_id IN (" + placeholders + ")", parameters)
            stats_rows = query("statistics_metadata", "SELECT id,statistic_id FROM statistics_meta WHERE statistic_id IN (" + placeholders + ")", parameters)
            if isinstance(state_rows, dict) or isinstance(stats_rows, dict):
                return output
            state_ids = {row["entity_id"]: row["metadata_id"] for row in state_rows}
            statistic_ids = {row["statistic_id"]: row["id"] for row in stats_rows}
            for entity in entity_ids:
                item = output["entities"][entity] = {}
                if entity in state_ids:
                    params = {"mid": state_ids[entity]}
                    base = f" FROM states FORCE INDEX({state_index}) WHERE metadata_id=:mid"
                    # Raw values are collected only for explicitly protected entities.
                    fields = "state_id,last_updated_ts,state" if entity in expected else "state_id,last_updated_ts"
                    item["latest_state"] = one("entity_latest_state", "SELECT " + fields + base + " ORDER BY last_updated_ts DESC LIMIT 1", params, state_index)
                    for block, field, operator, query_name in (
                        (exclusions, "new_states_after_exclusion", ">=", "post_exclusion"),
                        (retention, "raw_states_older_than_purge_cutoff", "<", "pre_purge"),
                    ):
                        if entity in block.get("entity_ids", []):
                            check = one(query_name, "SELECT 1 AS found" + base + f" AND last_updated_ts{operator}:cutoff LIMIT 1",
                                        {**params, "cutoff": block["cutoff_ts"]}, state_index)
                            item[field] = {**check, "exists": bool(check.get("found"))}
                else:
                    item["latest_state"] = {"checked": True, "no_metadata": True}
                    if entity in exclusions.get("entity_ids", []):
                        item["new_states_after_exclusion"] = {"checked": True, "exists": False, "no_metadata": True}
                    if entity in retention.get("entity_ids", []):
                        item["raw_states_older_than_purge_cutoff"] = {"checked": True, "exists": False, "no_metadata": True}
                if entity not in expected:
                    continue
                for table, field in (("statistics", "latest_statistics"),
                                     ("statistics_short_term", "latest_short_term_statistics")):
                    if entity not in statistic_ids:
                        item[field] = {"checked": True, "no_metadata": True}
                        continue
                    index = f"ix_{table}_statistic_id_start_ts"
                    item[field] = one(table + "_latest",
                        f"SELECT id,start_ts,created_ts,mean,min,max,state,sum FROM {table} FORCE INDEX({index}) WHERE metadata_id=:mid ORDER BY start_ts DESC LIMIT 1",
                        {"mid": statistic_ids[entity]}, index)
    finally:
        engine.dispose()
    output["query_seconds"] = round(output["query_seconds"], 3)
    output["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--config-root", default="/config")
    args = parser.parse_args()
    try:
        result = collect(json.loads(args.policy.read_text()), args.config_root)
    except Exception as error:
        print(json.dumps({"fatal_error_type": type(error).__name__, "credentials_printed": False}))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 1 if result["query_errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
