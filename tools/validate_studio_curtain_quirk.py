"""Offline protocol checks; execute with HA's installed Python packages.

QUIRK_FILE can override the default candidate in config/custom_zha_quirks/.
No radio is opened and no Home Assistant state is modified.
"""

import asyncio
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import AsyncMock, MagicMock

import zigpy.device
import zigpy.types as t
from zigpy.zcl.clusters.closures import WindowCovering
from zigpy.zdo.types import NodeDescriptor
import zhaquirks
from zha.quirks import DEVICE_REGISTRY
from zhaquirks.tuya import TuyaDatapointData


def make_device(manufacturer="_TZE204_r0jdjrvi"):
    application = MagicMock()
    application.get_sequence.return_value = 1
    device = zigpy.device.Device(application, t.EUI64.convert("00:11:22:33:44:55:66:77"), 0x1234)
    device.manufacturer = manufacturer
    device.model = "TS0601"
    device.node_desc = NodeDescriptor(
        logical_type=1, complex_descriptor_available=0,
        user_descriptor_available=0, reserved=0, aps_flags=0,
        frequency_band=8, mac_capability_flags=142, manufacturer_code=4417,
        maximum_buffer_size=66, maximum_incoming_transfer_size=66,
        server_mask=10752, maximum_outgoing_transfer_size=66,
        descriptor_capability_field=0,
    )
    endpoint = device.add_endpoint(1)
    endpoint.profile_id = 0x0104
    endpoint.device_type = 0x0051
    for cluster in (0x0000, 0x0004, 0x0005, 0xEF00):
        endpoint.add_input_cluster(cluster)
    for cluster in (0x000A, 0x0019):
        endpoint.add_output_cluster(cluster)
    green_power = device.add_endpoint(242)
    green_power.profile_id = 0xA1E0
    green_power.device_type = 0x0061
    green_power.add_output_cluster(0x0021)
    return device


async def main():
    default_quirk = (
        Path(__file__).resolve().parents[1]
        / "config/custom_zha_quirks/tuya_studio_curtain.py"
    )
    candidate = Path(os.environ.get("QUIRK_FILE", default_quirk))
    with tempfile.TemporaryDirectory(prefix="curtain-quirk-check-") as folder:
        Path(folder, "tuya_studio_curtain.py").write_text(candidate.read_text())
        zhaquirks.setup(folder)
        original = make_device()
        device = DEVICE_REGISTRY.resolve(original)
        cover = device.endpoints[1].in_clusters[0x0102]
        mcu = device.endpoints[1].in_clusters[0xEF00]
        assert device.endpoints[1].device_type == 0x0202
        assert device.endpoints[242].out_clusters[0x0021]
        unrelated = make_device("_TZE204_not_this_motor")
        assert DEVICE_REGISTRY.resolve(unrelated) is unrelated
        position_attr = WindowCovering.AttributeDefs.current_position_lift_percentage.id
        for dp in (2, 3):
            for value in (0, 25, 100):
                mcu._dp_2_attr_update(TuyaDatapointData(dp, value))
                assert cover.get(position_attr) == value
        mcu._dp_2_attr_update(TuyaDatapointData(3, -1))
        assert cover.get(position_attr) == 100
        mcu.command = AsyncMock()
        # ZCL open/close/stop map to Tuya enum 0/2/1 respectively.
        for command_id, expected in ((0, 0), (1, 2), (2, 1), (5, 75)):
            mcu.command.reset_mock()
            await cover.command(command_id, *([75] if command_id == 5 else []))
            await asyncio.sleep(0)
            assert mcu.command.call_count == 1, mcu.command.call_args_list
            packet = mcu.command.call_args.args[1]
            assert len(packet.datapoints) == 1
            datapoint = packet.datapoints[0]
            assert datapoint.dp == (2 if command_id == 5 else 1)
            assert datapoint.data.payload == expected
        for dp, name, value in ((5, "motor_direction", 1), (12, "motor_fault", True), (106, "motor_working_mode", 0)):
            mcu._dp_2_attr_update(TuyaDatapointData(dp, value))
            assert mcu.get(name) == value
        print(json.dumps({"ok": True, "checks": ["exact fingerprint", "endpoint preservation", "DP2 and DP3 reports", "invalid position ignored", "open-close-stop", "position writes DP2 only", "direction-fault-mode"]}))


if __name__ == "__main__":
    asyncio.run(main())
