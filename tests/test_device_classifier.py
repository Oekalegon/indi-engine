"""Tests for INDI device type classification."""

import pytest

from indi_engine.indi.device_classifier import classify_device
from indi_engine.indi.protocol.properties import IDevice
from indi_engine.server.serializer import serialize_device_info


# ---------------------------------------------------------------------------
# classify_device — single-role (primary signature)
# ---------------------------------------------------------------------------


class TestClassifyDevicePrimarySignatures:
    def test_mount_by_telescope_motion_ns(self):
        assert classify_device({"TELESCOPE_MOTION_NS", "CONNECTION"}) == ["mount"]

    def test_camera_by_ccd_exposure(self):
        assert classify_device({"CCD_EXPOSURE", "CONNECTION"}) == ["camera"]

    def test_focuser_by_focus_motion(self):
        assert classify_device({"FOCUS_MOTION", "CONNECTION"}) == ["focuser"]

    def test_filter_wheel_by_filter_slot(self):
        assert classify_device({"FILTER_SLOT", "CONNECTION"}) == ["filter_wheel"]

    def test_rotator_by_abs_rotator_angle(self):
        assert classify_device({"ABS_ROTATOR_ANGLE", "CONNECTION"}) == ["rotator"]

    def test_dome_by_dome_motion(self):
        assert classify_device({"DOME_MOTION", "CONNECTION"}) == ["dome"]

    def test_weather_by_weather_status(self):
        assert classify_device({"WEATHER_STATUS", "CONNECTION"}) == ["weather"]

    def test_gps_by_gps_refresh(self):
        assert classify_device({"GPS_REFRESH", "CONNECTION"}) == ["gps"]


# ---------------------------------------------------------------------------
# classify_device — fallback (multi-property) signatures
# ---------------------------------------------------------------------------


class TestClassifyDeviceFallbackSignatures:
    def test_mount_fallback_equatorial_and_slew_rate(self):
        assert classify_device({"EQUATORIAL_EOD_COORD", "TELESCOPE_SLEW_RATE"}) == ["mount"]

    def test_camera_fallback_ccd_frame_and_temperature(self):
        assert classify_device({"CCD_FRAME", "CCD_TEMPERATURE"}) == ["camera"]

    def test_focuser_fallback_abs_focus_position(self):
        assert classify_device({"ABS_FOCUS_POSITION"}) == ["focuser"]

    def test_dome_fallback_dome_shutter(self):
        assert classify_device({"DOME_SHUTTER", "CONNECTION"}) == ["dome"]

    def test_weather_fallback_weather_update(self):
        assert classify_device({"WEATHER_UPDATE", "CONNECTION"}) == ["weather"]

    def test_gps_fallback_system_time_update(self):
        assert classify_device({"SYSTEM_TIME_UPDATE", "CONNECTION"}) == ["gps"]


# ---------------------------------------------------------------------------
# classify_device — unknown
# ---------------------------------------------------------------------------


class TestClassifyDeviceUnknown:
    def test_empty_set_returns_empty_list(self):
        assert classify_device(set()) == []

    def test_universal_properties_only_returns_empty_list(self):
        assert classify_device({"CONNECTION", "DEVICE_PORT", "TIME_UTC"}) == []

    def test_single_unrelated_property_returns_empty_list(self):
        assert classify_device({"SOME_PROPRIETARY_PROP"}) == []


# ---------------------------------------------------------------------------
# classify_device — multi-role devices
# ---------------------------------------------------------------------------


class TestClassifyDeviceMultiRole:
    def test_camera_with_builtin_filter_wheel(self):
        # e.g. QSI or similar cameras with integrated filter wheel
        result = classify_device({"CCD_EXPOSURE", "FILTER_SLOT", "CONNECTION"})
        assert result == ["camera", "filter_wheel"]

    def test_focuser_with_builtin_rotator(self):
        # e.g. Pegasus FocusCube + rotator combo
        result = classify_device({"FOCUS_MOTION", "ABS_ROTATOR_ANGLE", "CONNECTION"})
        assert result == ["focuser", "rotator"]

    def test_mount_with_builtin_gps(self):
        result = classify_device({"TELESCOPE_MOTION_NS", "GPS_REFRESH", "CONNECTION"})
        assert result == ["mount", "gps"]

    def test_camera_with_filter_wheel_and_focuser(self):
        # Unusual but possible (e.g. all-in-one imaging controller)
        result = classify_device({"CCD_EXPOSURE", "FILTER_SLOT", "FOCUS_MOTION"})
        assert result == ["camera", "focuser", "filter_wheel"]

    def test_each_role_appears_only_once(self):
        # Primary + fallback signature both present for camera — should still be listed once
        result = classify_device({"CCD_EXPOSURE", "CCD_FRAME", "CCD_TEMPERATURE"})
        assert result.count("camera") == 1

    def test_result_follows_canonical_order(self):
        # filter_wheel before camera is NOT the canonical order; camera comes first
        result = classify_device({"FILTER_SLOT", "CCD_EXPOSURE"})
        assert result.index("camera") < result.index("filter_wheel")


# ---------------------------------------------------------------------------
# IDevice.device_types default
# ---------------------------------------------------------------------------


class TestIDeviceDefaultTypes:
    def test_device_types_defaults_to_empty_list(self):
        device = IDevice(name="Test Device")
        assert device.device_types == []

    def test_device_types_can_be_set(self):
        device = IDevice(name="Test Device", device_types=["camera", "filter_wheel"])
        assert device.device_types == ["camera", "filter_wheel"]


# ---------------------------------------------------------------------------
# serialize_device_info includes device_types
# ---------------------------------------------------------------------------


class TestSerializeDeviceInfoIncludesTypes:
    def _make_device(self, name: str, device_types: list = None) -> IDevice:
        device = IDevice(name=name)
        device.device_types = device_types or []
        return device

    def test_device_info_includes_device_types_empty(self):
        device = self._make_device("Test")
        result = serialize_device_info(device)
        assert "device_types" in result
        assert result["device_types"] == []

    def test_device_info_includes_single_type(self):
        device = self._make_device("CCD Simulator", device_types=["camera"])
        result = serialize_device_info(device)
        assert result["device_types"] == ["camera"]

    def test_device_info_includes_multiple_types(self):
        device = self._make_device("Combo Device", device_types=["camera", "filter_wheel"])
        result = serialize_device_info(device)
        assert result["device_types"] == ["camera", "filter_wheel"]
