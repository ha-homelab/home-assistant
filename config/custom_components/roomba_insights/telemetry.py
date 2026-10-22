"""Bounded, allowlisted telemetry. Deliberately independent of Home Assistant.

Local receipt time is never presented as the robot's observation time. A pose
has no validated relationship to a house floorplan, even when a pmap is known.
"""
from __future__ import annotations

from copy import deepcopy
import math
from itertools import islice
from typing import Any

MAX_COORDINATE = 1_000_000
MAX_MAPS = 25
MAX_REGIONS = 100


def number(value: Any, limit: float = MAX_COORDINATE):
    """Reject booleans, strings, non-finite and implausibly large numbers."""
    if type(value) not in (int, float) or abs(value) > limit or not math.isfinite(value):
        return None
    return value if abs(value) <= limit else None


def text(value: Any):
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        return None
    return value if all(c.isprintable() for c in value) else None


def pose(value: Any, received_at: str | None = None):
    if not isinstance(value, dict) or not isinstance(value.get("point"), dict):
        return None
    point = value["point"]
    x, y, theta = number(point.get("x")), number(point.get("y")), number(value.get("theta"), 360)
    if any(v is None for v in (x, y, theta)):
        return None
    return {
        "x": x, "y": y, "theta": theta,
        "observed_at": None,
        "received_at": received_at,
        "timestamp_quality": "local_received" if received_at else "not_provided",
        "frame_quality": "uncalibrated",
        "coordinate_source": "native_pose_point",
    }


def _fields(value, numeric=(), strings=()):
    if not isinstance(value, dict):
        return {}
    result = {}
    for key in numeric:
        v = number(value.get(key), 10_000_000_000)
        if v is not None:
            result[key] = v
    for key in strings:
        v = text(value.get(key))
        if v is not None:
            result[key] = v
    return result


def map_references(value: Any):
    """Recognize known ID/version forms without forwarding arbitrary payloads."""
    result = []
    candidates = value[:MAX_MAPS] if isinstance(value, list) else [value]
    for item in candidates:
        if not isinstance(item, dict):
            continue
        if (map_id := text(item.get("pmap_id"))) is not None:
            found = {"pmap_id": map_id}
            if version := text(item.get("user_pmapv_id")):
                found["user_pmapv_id"] = version
            result.append(found)
        else:
            for key, value in islice(item.items(), MAX_MAPS):
                # Local pmaps commonly contains [{"map-id": "version-id"}].
                if text(key) and text(value):
                    result.append({"pmap_id": key, "user_pmapv_id": value})
        if len(result) >= MAX_MAPS:
            break
    return result[:MAX_MAPS]


def last_command(value: Any):
    """Capture a request without making a truncated/partial replay valid."""
    result = _fields(value, ("time",), ("command", "pmap_id", "user_pmapv_id"))
    regions = value.get("regions") if isinstance(value, dict) else None
    result["regions_valid"] = False
    if isinstance(regions, list) and 0 < len(regions) <= MAX_REGIONS:
        cleaned, seen = [], set()
        for region in regions:
            entry = _fields(region, (), ("region_id", "type", "region_name", "region_type"))
            key = (entry.get("region_id"), entry.get("type"))
            if not key[0] or key[1] not in ("rid", "zid") or key in seen:
                return result
            seen.add(key)
            cleaned.append(entry)
        result["regions"] = cleaned
        result["regions_valid"] = True
    return result


class Telemetry:
    """Last known diagnostic snapshot, with separate coordinate provenance."""

    def __init__(self):
        self.data = {"position": None, "position_report_valid": False, "last_message_received_at": None}

    def update(self, reported: dict, *, received_at: str, initial=False, delta=None):
        if not isinstance(reported, dict):
            reported = {}
        data = self.data.copy()
        if not initial and isinstance(delta, dict) and delta:
            data["last_message_received_at"] = received_at
        if initial:
            data["position"] = pose(reported.get("pose"))
            data["position_report_valid"] = data["position"] is not None
        elif isinstance(delta, dict) and "pose" in delta:
            # Never combine a fresh x with a stale y/theta from the merged cache.
            fresh = pose(delta["pose"], received_at)
            data["position_report_valid"] = fresh is not None
            if fresh is not None:
                data["position"] = fresh
        cap = reported.get("cap")
        data["pose_supported"] = isinstance(cap, dict) and type(cap.get("pose")) is int and cap.get("pose") == 1
        data["cache_read_at"] = received_at
        data["mission"] = _fields(
            reported.get("cleanMissionStatus"),
            ("nMssn", "mssnM", "sqft", "mssnStrtTm", "error", "notReady"),
            ("cycle", "phase"),
        )
        data["maps"] = map_references(reported.get("pmaps"))
        if initial:
            data["last_command"] = last_command(reported.get("lastCommand"))
            data["last_command_source"] = "native_cache"
        elif isinstance(delta, dict) and "lastCommand" in delta:
            # The native library deep-merges dictionaries. Reading that merged
            # cache here could attach old room IDs to a new generic command.
            data["last_command"] = last_command(delta["lastCommand"])
            data["last_command_source"] = "message"
            data["last_command_received_at"] = received_at
        command = data.get("last_command", {})
        # A historical request can be learned, but this is not a map image or
        # proof that the request remains valid after a map-version change.
        has_request = bool(data.get("last_command_source") == "message" and command.get("command") == "start"
                           and command.get("pmap_id") and command.get("user_pmapv_id") and command.get("regions_valid"))
        known_versions = {m.get("user_pmapv_id") for m in data["maps"] if m["pmap_id"] == command.get("pmap_id")}
        data["room_request_observed"] = has_request
        data["room_request_matches_current_map"] = has_request and known_versions == {command.get("user_pmapv_id")}
        data["map_image_available"] = False

        self.data = data

    def snapshot(self, *, connected: bool, entry_state: str, source_entity_id=None):
        result = deepcopy(self.data)
        result.update(connected=connected, native_entry_state=entry_state, source_entity_id=source_entity_id)
        result["position_current"] = False  # No device observation timestamp.
        result["position_received_while_connected"] = bool(
            connected and result.get("position_report_valid") and result.get("position")
            and result["position"].get("received_at")
        )
        return result
