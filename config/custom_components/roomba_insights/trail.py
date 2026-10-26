"""Bounded, process-local traces of real Roomba pose messages.

This is uncalibrated relative odometry, not a floorplan, room map, or a measured
cleaning footprint. No initial cached pose is sampled and no data is persisted.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
import math
from threading import Lock

from .telemetry import pose

MAX_POINTS = 2048
MAX_GAP_SECONDS = 30
MIN_SAMPLE_SECONDS = 1
MAX_STEP = 500  # Native coordinate units; never advertised as meters.
IMAGE_SIZE = (640, 480)
MAX_PNG_BYTES = 1024 * 1024
BACKGROUND = (20, 31, 47)
TRAIL_COLOR = (69, 212, 189)


@dataclass(frozen=True)
class TrailSnapshot:
    generation: int
    revision: int
    segments: tuple[tuple[tuple[float, float], ...], ...]
    last_point_received_at: str | None
    status: str
    connected: bool
    truncated: bool

    @property
    def point_count(self):
        return sum(len(segment) for segment in self.segments)

    @property
    def has_path(self):
        return self.connected and any(len(segment) >= 2 for segment in self.segments)


def _receipt(value):
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value)
    except ValueError:
        return None
    return result if result.tzinfo is not None else None


def _identity(mission):
    if not isinstance(mission, dict):
        return None
    result = []
    for key in ("nMssn", "mssnStrtTm"):
        if key not in mission:
            continue
        value = mission[key]
        if type(value) is not int or value < 0 or value > 10_000_000_000:
            return None
        if key == "nMssn" or value > 0:
            result.append((key, value))
    return tuple(result) or None


class CleaningTrail:
    """Accept raw deltas; snapshots can safely cross MQTT/HA worker threads."""

    def __init__(self):
        self._lock = Lock()
        self._points = deque(maxlen=MAX_POINTS)
        self._generation = 0
        self._revision = 0
        self._segment = 0
        self._segment_open = False
        self._mission = None
        self._last_point_time = None
        self._last_point_received_at = None
        self._status = "waiting_for_pose"
        self._connected = False
        self._truncated = False

    def _status_changed(self, status):
        if self._status != status:
            self._status = status
            self._revision += 1

    def _break(self, reason):
        self._segment_open = False
        self._status_changed(reason)

    def _clear(self, reason):
        self._points.clear()
        self._mission = None
        self._last_point_time = None
        self._last_point_received_at = None
        self._segment_open = False
        self._segment = 0
        self._generation += 1
        self._revision += 1
        self._truncated = False
        self._status = reason

    def break_path(self, reason="disconnected"):
        with self._lock:
            self._break(reason)
            if reason == "disconnected" and self._connected:
                self._connected = False
                self._revision += 1

    def update(self, reported, delta, *, received_at):
        """Process one actual callback; do not call this for initial cache data."""
        with self._lock:
            if not isinstance(delta, dict) or not delta:
                return
            receipt = _receipt(received_at)
            if receipt is None:
                self._break("invalid_receipt_time")
                return
            if not self._connected:
                # Even with the same mission ID, reconnects may reset the
                # robot's coordinate origin. Do not bridge these sessions.
                self._clear("waiting_for_pose")
                self._connected = True
            mission = reported.get("cleanMissionStatus") if isinstance(reported, dict) else None
            identity = _identity(mission)
            incoming = delta.get("cleanMissionStatus")
            if "cleanMissionStatus" in delta:
                if not isinstance(incoming, dict):
                    self._clear("unknown_mission")
                    return
                identity_fields = {"nMssn", "mssnStrtTm"}.intersection(incoming)
                if identity_fields:
                    # Do not join an identity assembled from part of an old
                    # mission and part of a new message. A later complete pose
                    # can start a new trace once the native cache is coherent.
                    if _identity(incoming) is None or _identity(incoming) != identity:
                        self._clear("unknown_mission")
                        return
            if identity is None:
                self._clear("unknown_mission")
                return
            if identity != self._mission:
                # A new identity invalidates the old frame even if its first
                # report is inactive or has no pose at all.
                self._clear("waiting_for_pose")
                self._mission = identity
            active = mission.get("cycle") == "clean" and mission.get("phase") == "run"
            if not active:
                self._break("completed" if mission.get("cycle") == "none" else "not_cleaning")
                return
            if "pose" not in delta:
                return
            point = pose(delta["pose"], received_at)
            if point is None:
                self._break("invalid_pose_gap")
                return
            x, y = point["x"], point["y"]
            elapsed = None if self._last_point_time is None else (receipt - self._last_point_time).total_seconds()
            if elapsed is not None and elapsed < 0:
                self._break("receipt_order_gap")
                return
            if self._segment_open and self._points:
                _, old_x, old_y = self._points[-1]
                if elapsed > MAX_GAP_SECONDS:
                    self._break("receipt_gap")
                elif math.hypot(x - old_x, y - old_y) > MAX_STEP:
                    self._break("coordinate_jump")
                elif (x, y) == (old_x, old_y) or elapsed < MIN_SAMPLE_SECONDS:
                    return
            if not self._segment_open:
                self._segment += 1
                self._segment_open = True
            if len(self._points) == MAX_POINTS:
                self._truncated = True
            self._points.append((self._segment, x, y))
            self._last_point_time = receipt
            self._last_point_received_at = received_at
            self._status = "collecting"
            self._revision += 1

    def snapshot(self):
        with self._lock:
            segments = []
            previous = None
            for number, x, y in self._points:
                if number != previous:
                    segments.append([])
                    previous = number
                segments[-1].append((x, y))
            return TrailSnapshot(
                self._generation, self._revision,
                tuple(tuple(segment) for segment in segments),
                self._last_point_received_at, self._status, self._connected, self._truncated,
            )


def project_segments(snapshot):
    """Aspect-preserving plot in native relative coordinates, without a map."""
    points = [point for segment in snapshot.segments for point in segment]
    if not points:
        return ()
    xs, ys = zip(*points)
    left, top, right, bottom = 36, 88, IMAGE_SIZE[0] - 36, IMAGE_SIZE[1] - 68
    min_x, max_y = min(xs), max(ys)
    dx, dy = max(max(xs) - min_x, 1), max(max_y - min(ys), 1)
    scale = min((right - left) / dx, (bottom - top) / dy)
    offset_x = (left + right - dx * scale) / 2
    offset_y = (top + bottom - dy * scale) / 2
    return tuple(tuple((round(offset_x + (x - min_x) * scale),
                        round(offset_y + (max_y - y) * scale)) for x, y in segment)
                 for segment in snapshot.segments)


def render_png(snapshot):
    """Render a bounded immutable snapshot in a worker, never an MQTT callback."""
    if not snapshot.has_path or snapshot.point_count > MAX_POINTS:
        return None
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", IMAGE_SIZE, BACKGROUND)
    draw = ImageDraw.Draw(image)
    title_font = ImageFont.load_default(size=22)
    label_font = ImageFont.load_default(size=16)
    caption_font = ImageFont.load_default(size=12)
    draw.text((24, 16), "Relative cleaning path", font=title_font, fill=(238, 246, 255))
    draw.text((24, 45), "Uncalibrated odometry - not a house map", font=label_font, fill=(170, 190, 210))
    projected = project_segments(snapshot)
    for segment in projected:
        if len(segment) >= 2:
            draw.line(segment, fill=TRAIL_COLOR, width=3)
        for x, y in segment:
            draw.ellipse((x - 1, y - 1, x + 1, y + 1), fill=TRAIL_COLOR)
    for point, color in ((projected[0][0], (240, 246, 255)), (projected[-1][-1], (255, 204, 90))):
        x, y = point
        draw.ellipse((x - 5, y - 5, x + 5, y + 5), outline=color, width=2)
    suffix = " | older points omitted" if snapshot.truncated else ""
    draw.text((24, IMAGE_SIZE[1] - 46),
              f"{snapshot.point_count} sampled points | {len(projected)} segments | {snapshot.status}{suffix}",
              font=caption_font, fill=(170, 190, 210))
    draw.text((24, IMAGE_SIZE[1] - 26),
              "Last pose received: " + (snapshot.last_point_received_at or "unknown"),
              font=caption_font, fill=(170, 190, 210))
    output = BytesIO()
    image.save(output, format="PNG", optimize=False)
    content = output.getvalue()
    return content if len(content) <= MAX_PNG_BYTES else None
