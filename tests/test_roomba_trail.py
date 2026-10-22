"""Real-delta path boundaries, bounded rendering and HA image lifecycle."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from io import BytesIO
import importlib.util
import os
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "config/custom_components/roomba_insights"
PACKAGE = "_roomba_trail_unit"
package = ModuleType(PACKAGE)
package.__path__ = [str(COMPONENT)]
sys.modules[PACKAGE] = package
spec = importlib.util.spec_from_file_location(f"{PACKAGE}.trail", COMPONENT / "trail.py")
trail = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = trail
spec.loader.exec_module(trail)

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)
MISSION = {"nMssn": 1, "mssnStrtTm": 100, "cycle": "clean", "phase": "run"}


def point(x=0, y=0):
    return {"point": {"x": x, "y": y}, "theta": 0}


def receipt(seconds):
    return (BASE + timedelta(seconds=seconds)).isoformat()


def feed(value, x=0, y=0, at=0, mission=None, delta=None):
    reported = {"cleanMissionStatus": deepcopy(MISSION if mission is None else mission), "pose": point(x, y)}
    value.update(reported, {"pose": point(x, y)} if delta is None else delta, received_at=receipt(at))
    return value.snapshot()


def path_snapshot():
    value = trail.CleaningTrail()
    feed(value)
    return feed(value, 10, 10, 2)


class TrailTest(unittest.TestCase):
    def setUp(self):
        self.value = trail.CleaningTrail()

    def test_no_initial_cache_or_other_messages_become_points(self):
        for delta in [None, {}, [], {"batPct": 90}]:
            self.value.update({"cleanMissionStatus": MISSION, "pose": point()}, delta,
                              received_at=receipt(0))
        self.assertEqual(self.value.snapshot().point_count, 0)
        self.assertFalse(self.value.snapshot().has_path)

    def test_actual_complete_zero_pose_is_accepted(self):
        first = feed(self.value)
        second = feed(self.value, 10, 2, 2)
        self.assertEqual(first.segments, (((0, 0),),))
        self.assertTrue(second.has_path)
        self.assertEqual(second.last_point_received_at, receipt(2))
        self.assertEqual(second.segments, (((0, 0), (10, 2)),))

    def test_only_complete_valid_delta_not_merged_cache(self):
        invalid = [None, {}, {"point": {"x": 10}}, {"point": {"x": 10, "y": 20}},
                   {"point": {"x": True, "y": 0}, "theta": 0}, point(float("nan")),
                   point(float("inf")), point(10**1000)]
        for candidate in invalid:
            with self.subTest(candidate=str(candidate)[:60]):
                value = trail.CleaningTrail()
                feed(value)
                feed(value, 5, at=2, delta={"pose": candidate})
                result = feed(value, 10, at=4)
                self.assertEqual(result.segments, (((0, 0),), ((10, 0),)))
                self.assertFalse(result.has_path)

    def test_mission_requires_explicit_valid_identity(self):
        for mission in [{}, {"phase": "run", "cycle": "clean"},
                        dict(MISSION, nMssn=True), dict(MISSION, mssnStrtTm="100"),
                        dict(MISSION, nMssn=-1), dict(MISSION, nMssn=10**100)]:
            value = trail.CleaningTrail()
            feed(value, mission=mission)
            result = feed(value, 10, at=2, mission=mission)
            self.assertFalse(result.has_path)
            self.assertEqual(result.point_count, 0)
        for mission in [{"nMssn": 0, "phase": "run", "cycle": "clean"},
                        {"mssnStrtTm": 100, "phase": "run", "cycle": "clean"},
                        dict(MISSION, mssnStrtTm=0)]:
            value = trail.CleaningTrail()
            feed(value, mission=mission, delta={"pose": point(), "cleanMissionStatus": mission})
            self.assertTrue(feed(value, 10, at=2, mission=mission).has_path)

    def test_partial_or_malformed_identity_update_clears_previous_frame(self):
        for incoming in [None, [], {"nMssn": 2}, {"mssnStrtTm": None}, {"nMssn": True}]:
            value = trail.CleaningTrail()
            feed(value)
            feed(value, 5, at=2)
            result = feed(value, 10, at=4, delta={"pose": point(10), "cleanMissionStatus": incoming})
            self.assertEqual(result.point_count, 0)
            result = feed(value, 20, at=6)
            self.assertEqual(result.segments, (((20, 0),),))

    def test_new_mission_clears_old_trace_even_before_new_pose(self):
        feed(self.value)
        old = feed(self.value, 10, at=2)
        mission = dict(MISSION, nMssn=2, mssnStrtTm=200)
        new = feed(self.value, at=4, mission=mission, delta={"cleanMissionStatus": mission})
        self.assertGreater(new.generation, old.generation)
        self.assertEqual(new.point_count, 0)
        self.assertEqual(feed(self.value, 50, at=6, mission=mission).segments, (((50, 0),),))

    def test_noncleaning_and_unknown_phase_break_without_adding_coordinates(self):
        for phase, cycle in [("charge", "clean"), (None, "clean"), ("run", None), ("charge", "none")]:
            value = trail.CleaningTrail()
            feed(value)
            feed(value, 10, at=2)
            mission = dict(MISSION, phase=phase, cycle=cycle)
            result = feed(value, 20, at=4, mission=mission, delta={"pose": point(20), "cleanMissionStatus": mission})
            self.assertEqual(result.point_count, 2)
            self.assertEqual(feed(value, 30, at=6).segments, (((0, 0), (10, 0)), ((30, 0),)))

    def test_new_inactive_mission_invalidates_old_frame(self):
        feed(self.value)
        feed(self.value, 10, at=2)
        mission = dict(MISSION, nMssn=2, mssnStrtTm=200, phase="charge")
        result = feed(self.value, at=4, mission=mission, delta={"cleanMissionStatus": mission})
        self.assertEqual(result.point_count, 0)
        self.assertFalse(result.has_path)

    def test_disconnect_is_idempotent_and_new_session_cannot_bridge(self):
        feed(self.value)
        old = feed(self.value, 10, at=2)
        self.value.break_path()
        disconnected = self.value.snapshot()
        self.assertFalse(disconnected.has_path)
        self.assertEqual(disconnected.point_count, 2)
        for _ in range(100):
            self.value.break_path()
        self.assertEqual(self.value.snapshot(), disconnected)
        new = feed(self.value, 20, at=4)
        self.assertGreater(new.generation, old.generation)
        self.assertEqual(new.segments, (((20, 0),),))

    def test_time_gaps_jumps_and_reverse_receipts_never_connect(self):
        feed(self.value)
        feed(self.value, 10, at=2)
        feed(self.value, 20, at=40)
        feed(self.value, 1000, at=42)
        feed(self.value, 1010, at=41)  # rejected out-of-order receipt
        result = feed(self.value, 1020, at=44)
        self.assertEqual(result.segments, (((0, 0), (10, 0)), ((20, 0),), ((1000, 0),), ((1020, 0),)))

    def test_bad_receipt_breaks_and_does_not_refresh_last_point(self):
        feed(self.value)
        for when in [None, "bad", "2026-01-01T00:00:00"]:
            self.value.update({"cleanMissionStatus": MISSION}, {"pose": point(10)}, received_at=when)
        self.assertEqual(self.value.snapshot().last_point_received_at, receipt(0))
        self.assertEqual(feed(self.value, 20, at=2).segments, (((0, 0),), ((20, 0),)))

    def test_sampling_duplicate_and_too_frequent_points_do_not_grow_trace(self):
        feed(self.value)
        feed(self.value, 10, at=0.5)
        feed(self.value, at=2)
        result = feed(self.value, 10, at=3)
        self.assertEqual(result.point_count, 2)
        self.assertEqual(result.last_point_received_at, receipt(3))

    def test_points_and_segments_bounded_under_boundary_flood(self):
        for i in range(trail.MAX_POINTS + 100):
            feed(self.value, i, at=i * 2)
            self.value.break_path("invalid_pose_gap")
        result = self.value.snapshot()
        self.assertEqual(result.point_count, trail.MAX_POINTS)
        self.assertEqual(len(result.segments), trail.MAX_POINTS)
        self.assertTrue(result.truncated)
        self.assertFalse(result.has_path)
        for _ in range(5000):
            self.value.break_path("invalid_pose_gap")
        self.assertEqual(self.value.snapshot(), result)
        for i in range(5000):
            feed(self.value, at=i, mission={})
        self.assertEqual(self.value.snapshot().point_count, 0)
        self.assertEqual(self.value.snapshot().segments, ())

    def test_snapshot_is_immutable_and_detached_from_input(self):
        p = point()
        self.value.update({"cleanMissionStatus": MISSION}, {"pose": p}, received_at=receipt(0))
        result = self.value.snapshot()
        p["point"]["x"] = 999
        feed(self.value, 10, at=2)
        self.assertEqual(result.segments, (((0, 0),),))
        with self.assertRaises(FrozenInstanceError):
            result.connected = False

    def test_parallel_break_and_snapshot_keep_consistent_bounds(self):
        from concurrent.futures import ThreadPoolExecutor
        def writer():
            for i in range(300):
                feed(self.value, i, at=i * 2)
        def breaker():
            for _ in range(300):
                self.value.break_path()
                snapshot = self.value.snapshot()
                self.assertLessEqual(snapshot.point_count, trail.MAX_POINTS)
                self.assertTrue(all(segment for segment in snapshot.segments))
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(writer), pool.submit(breaker), pool.submit(breaker)]
            for future in futures:
                future.result()
        self.value.break_path()
        self.assertFalse(self.value.snapshot().has_path)


try:
    from PIL import Image
except ImportError:
    PIL_AVAILABLE = False
else:
    PIL_AVAILABLE = True


@unittest.skipUnless(PIL_AVAILABLE, "Requires deployed Pillow for pixel invariants")
class RenderTest(unittest.TestCase):
    def test_no_placeholder_when_no_real_line_exists(self):
        value = trail.CleaningTrail()
        self.assertIsNone(trail.render_png(value.snapshot()))
        self.assertIsNone(trail.render_png(feed(value)))
        feed(value, 10, at=2)
        value.break_path()
        self.assertIsNone(trail.render_png(value.snapshot()))

    def test_fixed_png_budget_no_metadata_and_no_line_across_boundary(self):
        value = trail.CleaningTrail()
        feed(value, 0, 0, 0)
        feed(value, 10, 0, 2)
        value.break_path("invalid_pose_gap")
        feed(value, 20, 0, 4)
        result = feed(value, 30, 0, 6)
        content = trail.render_png(result)
        self.assertLessEqual(len(content), trail.MAX_PNG_BYTES)
        picture = Image.open(BytesIO(content))
        self.assertEqual(picture.size, trail.IMAGE_SIZE)
        self.assertEqual(picture.format, "PNG")
        self.assertEqual(picture.info, {})
        segments = trail.project_segments(result)
        inside = (round((segments[0][0][0] + segments[0][1][0]) / 2), segments[0][0][1])
        gap = (round((segments[0][1][0] + segments[1][0][0]) / 2), segments[0][1][1])
        self.assertEqual(picture.getpixel(inside), trail.TRAIL_COLOR)
        self.assertEqual(picture.getpixel(gap), trail.BACKGROUND)

    def test_maximum_trace_render_remains_bounded(self):
        value = trail.CleaningTrail()
        for i in range(trail.MAX_POINTS * 2):
            feed(value, i % 100, (i // 100) % 100, i * 2)
        snapshot = value.snapshot()
        self.assertEqual(snapshot.point_count, trail.MAX_POINTS)
        self.assertTrue(snapshot.truncated)
        self.assertLess(len(trail.render_png(snapshot)), trail.MAX_PNG_BYTES)


try:
    from homeassistant.core import HomeAssistant
except ImportError:
    HA_AVAILABLE = False
else:
    HA_AVAILABLE = True
    sys.path.insert(0, str(ROOT / "config"))
    from custom_components.roomba_insights import image as image_module

if os.environ.get("REQUIRE_HA_RUNTIME") == "1" and not (HA_AVAILABLE and PIL_AVAILABLE):
    raise RuntimeError("Home Assistant and deployed Pillow are required for trail runtime tests")


@unittest.skipUnless(HA_AVAILABLE, "Requires Home Assistant runtime for ImageEntity tests")
class ImageLifecycleTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import tempfile
        from homeassistant import loader
        from homeassistant.bootstrap import async_load_base_functionality
        from homeassistant.config_entries import ConfigEntries
        self.temp = tempfile.TemporaryDirectory(prefix="roomba-trail-test-")
        self.hass = HomeAssistant(self.temp.name)
        loader.async_setup(self.hass)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        self.hass.config.skip_pip = True
        self.assertTrue(await async_load_base_functionality(self.hass))
        self.snapshot = path_snapshot()
        manager = SimpleNamespace(hass=self.hass, snapshot_trail=lambda _: self.snapshot,
                                  entities={"synthetic": SimpleNamespace(source_entity_id="vacuum.example")})
        self.entity = image_module.RoombaTrailImage(manager, SimpleNamespace(entry_id="synthetic", title="Test robot"))
        self.entity.hass = self.hass
        self.entity.entity_id = "image.test_robot_relative_cleaning_path"
        self.entity.async_write_ha_state = Mock()

    async def asyncTearDown(self):
        if not self.entity._removed:
            await self.entity.async_will_remove_from_hass()
        await self.hass.async_stop(force=True)
        self.temp.cleanup()

    async def test_published_image_is_cached_executor_output_and_attributes_are_private(self):
        await self.entity.async_added_to_hass()
        task = self.entity._render_task
        self.assertIsNotNone(task)
        await task
        content = await self.entity.async_image()
        self.assertIsNotNone(content)
        self.assertIs(await self.entity.async_image(), content)
        self.assertTrue(self.entity.available)
        self.assertEqual(self.entity.content_type, "image/png")
        attrs = self.entity.extra_state_attributes
        self.assertEqual(attrs["source_entity_id"], "vacuum.example")
        self.assertEqual(attrs["last_point_received_at"], receipt(2))
        self.assertFalse(attrs["is_house_map"])
        self.assertNotIn("segments", attrs)
        self.assertNotIn("coordinates", attrs)
        self.assertNotIn("synthetic", repr(attrs))
        self.assertNotIn("Test robot", repr(attrs))
        self.assertIsNone(attrs["observed_at"])
        self.assertGreater(len(self.entity.access_tokens), 0)

    async def test_throttle_coalesces_and_disconnection_clears_image(self):
        self.entity.async_update_trail()
        await self.entity._render_task
        self.snapshot = replace(self.snapshot, revision=self.snapshot.revision + 1)
        self.entity.async_update_trail()
        timer = self.entity._timer
        self.assertIsNotNone(timer)
        for i in range(20):
            self.snapshot = replace(self.snapshot, revision=self.snapshot.revision + 1)
            self.entity.async_update_trail()
        self.assertIs(self.entity._timer, timer)
        self.assertIsNone(self.entity._render_task)
        self.snapshot = replace(self.snapshot, connected=False)
        self.entity.async_update_trail()
        self.assertIsNone(await self.entity.async_image())
        self.assertFalse(self.entity.available)
        self.assertIsNone(self.entity._timer)
        self.assertIsNone(self.entity.image_last_updated)

    async def test_stale_worker_result_is_never_published(self):
        import asyncio
        entered = asyncio.Event()
        release = asyncio.Event()
        async def executor(_fn, _snapshot):
            entered.set()
            await release.wait()
            return b"obsolete"
        with patch.object(self.hass, "async_add_executor_job", side_effect=executor):
            self.entity.async_update_trail()
            task = self.entity._render_task
            await entered.wait()
            self.snapshot = replace(self.snapshot, generation=self.snapshot.generation + 1, revision=self.snapshot.revision + 1)
            self.entity.async_update_trail()
            release.set()
            await task
        self.assertIsNone(await self.entity.async_image())
        self.assertIsNone(self.entity._displayed)
        self.assertIsNotNone(self.entity._timer)

    async def test_failed_render_does_not_retry_same_snapshot_forever(self):
        with patch.object(self.hass, "async_add_executor_job", new=AsyncMock(side_effect=ValueError("synthetic failure"))) as executor:
            with self.assertLogs(image_module.__name__, level="ERROR"):
                self.entity.async_update_trail()
                await self.entity._render_task
            self.entity.async_update_trail()
            self.assertEqual(executor.await_count, 1)
        self.assertFalse(self.entity.available)
        self.assertIsNone(self.entity._timer)

    async def test_removal_cancels_pending_worker_and_never_writes_after_remove(self):
        import asyncio
        entered = asyncio.Event()
        async def executor(_fn, _snapshot):
            entered.set()
            await asyncio.Event().wait()
        with patch.object(self.hass, "async_add_executor_job", side_effect=executor):
            self.entity.async_update_trail()
            task = self.entity._render_task
            await entered.wait()
            await self.entity.async_will_remove_from_hass()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.entity.async_update_trail()
        self.entity.async_write_ha_state.assert_not_called()
        self.assertIsNone(await self.entity.async_image())
        self.assertIsNone(self.entity._timer)


if __name__ == "__main__":
    unittest.main()
