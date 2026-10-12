"""Local ZHA support for the Tuya _TZE204_r0jdjrvi curtain motor.

DP definitions: zigbee-herdsman-converters, TS0601_cover_8.
Unlike many Tuya motors, raw position is 0=open and 100=closed, matching ZCL.
DP 2 is the target position; DP 3 is a report, never a command destination.
"""

import zigpy.types as t
from zigpy.zcl.clusters.closures import WindowCovering

from zhaquirks.builder import EntityType
from zhaquirks.tuya.builder import TuyaQuirkBuilder
from zhaquirks.tuya.mcu import TuyaMCUCluster


class MotorDirection(t.enum8):
    """Direction values used by this motor."""

    Forward = 0
    Back = 1


class MotorWorkingMode(t.enum8):
    """Continuous or intermittent operation."""

    Continuous = 0
    Intermittently = 1


class CurtainMCUCluster(TuyaMCUCluster):
    """Accept both position reports, but write only the target datapoint."""

    def get_dp_mapping(self, endpoint_id, attribute_name):
        mapping = super().get_dp_mapping(endpoint_id, attribute_name)
        if attribute_name == WindowCovering.AttributeDefs.current_position_lift_percentage.name:
            mapping.pop(3, None)
        return mapping

    def _dp_2_attr_update(self, datapoint):
        if datapoint.dp in (2, 3) and not 0 <= datapoint.data.payload <= 100:
            # An uncalibrated motor can report a sentinel instead of a position.
            self.debug("Ignoring uncalibrated position: %s", datapoint.data.payload)
            return
        super()._dp_2_attr_update(datapoint)


(
    TuyaQuirkBuilder("_TZE204_r0jdjrvi", "TS0601")
    .tuya_cover(control_dp=1, position_state_dp=3, position_control_dp=2, invert=False)
    .tuya_enum(
        dp_id=5,
        attribute_name="motor_direction",
        enum_class=MotorDirection,
        entity_type=EntityType.CONFIG,
        translation_key="motor_direction",
        fallback_name="Motor direction",
    )
    .tuya_binary_sensor(
        dp_id=12,
        attribute_name="motor_fault",
        translation_key="motor_fault",
        fallback_name="Motor fault",
    )
    .tuya_enum(
        dp_id=106,
        attribute_name="motor_working_mode",
        enum_class=MotorWorkingMode,
        entity_type=EntityType.CONFIG,
        translation_key="motor_working_mode",
        fallback_name="Motor working mode",
    )
    .skip_configuration()
    .add_to_registry(replacement_cluster=CurtainMCUCluster)
)
