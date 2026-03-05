"""Tests for the "nice to have" PyIndi compatibility features:

- BLOBHandling enum and C-style constants
- Typed property wrappers (PropertyNumber, PropertySwitch, etc.)
- IDevice typed getters (getNumber, getText, getSwitch, getLight, getBLOB)
- BLOB parsing (defBLOBVector / setBLOBVector)
- newBLOB callback
- IPropertyElement BLOB accessors (getblobdata, getbloblen, getblobformat)
- setBLOBMode accepts BLOBHandling enum
"""

import base64
import pytest
from unittest.mock import MagicMock

from indi_engine.indi.protocol.client import PurePythonIndiClient
from indi_engine.indi.protocol.constants import (
    IndiPropertyType, IndiPropertyState, IndiPropertyPerm, IndiSwitchRule,
    BLOBHandling,
    # C-style constants
    INDI_NUMBER, INDI_TEXT, INDI_SWITCH, INDI_LIGHT, INDI_BLOB,
    IPS_IDLE, IPS_OK, IPS_BUSY, IPS_ALERT,
    ISS_OFF, ISS_ON,
    IPV_RO, IPV_WO, IPV_RW,
    ISR_ONEOFMANY, ISR_ATMOST_ONE, ISR_NOFMANY,
    B_NEVER, B_ALSO, B_ONLY,
)
from indi_engine.indi.protocol.properties import (
    IProperty, IPropertyElement, IDevice,
    PropertyNumber, PropertyText, PropertySwitch, PropertyLight, PropertyBlob,
    INumberVectorProperty, ITextVectorProperty, ISwitchVectorProperty,
    ILightVectorProperty, IBLOBVectorProperty,
)
from indi_engine.indi.protocol.parser import IndiXmlParser
from indi_engine.indi.protocol.errors import IndiDisconnectedError


def _make_client(connected: bool = True) -> PurePythonIndiClient:
    client = PurePythonIndiClient()
    client._transport = MagicMock()
    client._transport.is_connected.return_value = connected
    return client


# ---------------------------------------------------------------------------
# BLOBHandling enum
# ---------------------------------------------------------------------------

class TestBLOBHandlingEnum:

    def test_values(self):
        assert BLOBHandling.B_NEVER.value == "Never"
        assert BLOBHandling.B_ALSO.value == "Also"
        assert BLOBHandling.B_ONLY.value == "Only"

    def test_set_blob_mode_accepts_enum(self):
        client = _make_client()
        client.setBLOBMode(BLOBHandling.B_ALSO, device="CCD")
        sent = client._transport.send_message.call_args[0][0]
        assert "Also" in sent

    def test_set_blob_mode_accepts_string(self):
        client = _make_client()
        client.setBLOBMode("Only", device="CCD")
        sent = client._transport.send_message.call_args[0][0]
        assert "Only" in sent

    def test_set_blob_mode_rejects_invalid(self):
        client = _make_client()
        with pytest.raises(ValueError):
            client.setBLOBMode("BadMode", device="CCD")


# ---------------------------------------------------------------------------
# C-style constants
# ---------------------------------------------------------------------------

class TestCStyleConstants:

    def test_property_type_aliases(self):
        assert INDI_NUMBER == IndiPropertyType.NUMBER
        assert INDI_TEXT   == IndiPropertyType.TEXT
        assert INDI_SWITCH == IndiPropertyType.SWITCH
        assert INDI_LIGHT  == IndiPropertyType.LIGHT
        assert INDI_BLOB   == IndiPropertyType.BLOB

    def test_property_state_aliases(self):
        assert IPS_IDLE  == IndiPropertyState.IDLE
        assert IPS_OK    == IndiPropertyState.OK
        assert IPS_BUSY  == IndiPropertyState.BUSY
        assert IPS_ALERT == IndiPropertyState.ALERT

    def test_switch_state_aliases(self):
        assert ISS_ON  == "On"
        assert ISS_OFF == "Off"

    def test_permission_aliases(self):
        assert IPV_RO == IndiPropertyPerm.RO
        assert IPV_WO == IndiPropertyPerm.WO
        assert IPV_RW == IndiPropertyPerm.RW

    def test_switch_rule_aliases(self):
        assert ISR_ONEOFMANY  == IndiSwitchRule.ONE_OF_MANY
        assert ISR_ATMOST_ONE == IndiSwitchRule.AT_MOST_ONE
        assert ISR_NOFMANY    == IndiSwitchRule.ANY_OF_MANY

    def test_blob_handling_aliases(self):
        assert B_NEVER == BLOBHandling.B_NEVER
        assert B_ALSO  == BLOBHandling.B_ALSO
        assert B_ONLY  == BLOBHandling.B_ONLY

    def test_c_style_type_comparison(self):
        """Code written for PyIndi can compare getType() against INDI_NUMBER."""
        prop = IProperty(device_name="Dev", name="RADEC", type=IndiPropertyType.NUMBER)
        assert prop.getType() == INDI_NUMBER
        assert prop.getType() != INDI_SWITCH


# ---------------------------------------------------------------------------
# Typed property wrappers
# ---------------------------------------------------------------------------

class TestTypedPropertyWrappers:

    def _make_prop(self, ptype):
        prop = IProperty(device_name="Dev", name="PROP", type=ptype)
        prop.elements["E1"] = IPropertyElement(name="E1", value="1.0", type=ptype)
        prop.elements["E2"] = IPropertyElement(name="E2", value="2.0", type=ptype)
        return prop

    def test_property_number_delegates(self):
        prop = self._make_prop(IndiPropertyType.NUMBER)
        np = PropertyNumber(prop)
        assert np.getName() == "PROP"
        assert np.getDeviceName() == "Dev"
        assert len(np) == 2

    def test_property_number_iteration(self):
        prop = self._make_prop(IndiPropertyType.NUMBER)
        np = PropertyNumber(prop)
        names = [e.name for e in np]
        assert names == ["E1", "E2"]

    def test_property_number_indexing(self):
        prop = self._make_prop(IndiPropertyType.NUMBER)
        np = PropertyNumber(prop)
        assert np[0].name == "E1"

    def test_property_switch_delegates(self):
        prop = self._make_prop(IndiPropertyType.SWITCH)
        sp = PropertySwitch(prop)
        assert sp.getType() == IndiPropertyType.SWITCH

    def test_property_text_delegates(self):
        prop = self._make_prop(IndiPropertyType.TEXT)
        tp = PropertyText(prop)
        assert tp.getType() == IndiPropertyType.TEXT

    def test_property_light_delegates(self):
        prop = self._make_prop(IndiPropertyType.LIGHT)
        lp = PropertyLight(prop)
        assert lp.getType() == IndiPropertyType.LIGHT

    def test_property_blob_delegates(self):
        prop = self._make_prop(IndiPropertyType.BLOB)
        bp = PropertyBlob(prop)
        assert bp.getType() == IndiPropertyType.BLOB

    def test_legacy_aliases(self):
        prop = self._make_prop(IndiPropertyType.NUMBER)
        assert INumberVectorProperty is PropertyNumber
        assert ITextVectorProperty is PropertyText
        assert ISwitchVectorProperty is PropertySwitch
        assert ILightVectorProperty is PropertyLight
        assert IBLOBVectorProperty is PropertyBlob


# ---------------------------------------------------------------------------
# IDevice typed getters
# ---------------------------------------------------------------------------

class TestIDeviceTypedGetters:

    def _make_device_with_props(self):
        device = IDevice(name="CCD Simulator")
        device.properties["EXPOSURE"] = IProperty(
            device_name="CCD Simulator", name="EXPOSURE", type=IndiPropertyType.NUMBER
        )
        device.properties["UPLOAD_MODE"] = IProperty(
            device_name="CCD Simulator", name="UPLOAD_MODE", type=IndiPropertyType.SWITCH
        )
        device.properties["FITS_HEADER"] = IProperty(
            device_name="CCD Simulator", name="FITS_HEADER", type=IndiPropertyType.TEXT
        )
        device.properties["CCD_STATUS"] = IProperty(
            device_name="CCD Simulator", name="CCD_STATUS", type=IndiPropertyType.LIGHT
        )
        device.properties["CCD1"] = IProperty(
            device_name="CCD Simulator", name="CCD1", type=IndiPropertyType.BLOB
        )
        return device

    def test_get_number_returns_prop(self):
        device = self._make_device_with_props()
        prop = device.getNumber("EXPOSURE")
        assert prop is not None
        assert prop.type == IndiPropertyType.NUMBER

    def test_get_number_wrong_type_returns_none(self):
        device = self._make_device_with_props()
        assert device.getNumber("UPLOAD_MODE") is None

    def test_get_number_missing_returns_none(self):
        device = self._make_device_with_props()
        assert device.getNumber("NONEXISTENT") is None

    def test_get_text_returns_prop(self):
        device = self._make_device_with_props()
        prop = device.getText("FITS_HEADER")
        assert prop is not None
        assert prop.type == IndiPropertyType.TEXT

    def test_get_switch_returns_prop(self):
        device = self._make_device_with_props()
        prop = device.getSwitch("UPLOAD_MODE")
        assert prop is not None
        assert prop.type == IndiPropertyType.SWITCH

    def test_get_light_returns_prop(self):
        device = self._make_device_with_props()
        prop = device.getLight("CCD_STATUS")
        assert prop is not None
        assert prop.type == IndiPropertyType.LIGHT

    def test_get_blob_returns_prop(self):
        device = self._make_device_with_props()
        prop = device.getBLOB("CCD1")
        assert prop is not None
        assert prop.type == IndiPropertyType.BLOB


# ---------------------------------------------------------------------------
# BLOB parsing
# ---------------------------------------------------------------------------

class TestBlobParsing:
    parser = IndiXmlParser()

    def test_parse_def_blob_vector(self):
        xml = (
            b'<defBLOBVector device="CCD Simulator" name="CCD1" '
            b'label="Image Data" group="Images" state="Idle" perm="ro">'
            b'<defBLOB name="CCD1" label="Image"/>'
            b'</defBLOBVector>'
        )
        msg = self.parser.parse_message(xml)
        assert msg is not None
        assert msg.data["type"] == "blob"
        assert "CCD1" in msg.data["elements"]
        assert msg.data["elements"]["CCD1"]["value"] == b""

    def test_parse_set_blob_vector(self):
        raw = b"\x00\x01\x02\x03\xff"
        encoded = base64.b64encode(raw).decode()
        xml = (
            f'<setBLOBVector device="CCD Simulator" name="CCD1" state="Ok">'
            f'<oneBLOB name="CCD1" size="{len(raw)}" enclen="{len(encoded)}" format=".fits">'
            f'{encoded}'
            f'</oneBLOB>'
            f'</setBLOBVector>'
        ).encode()
        msg = self.parser.parse_message(xml)
        assert msg is not None
        assert msg.data["type"] == "blob"
        elem = msg.data["elements"]["CCD1"]
        assert elem["value"] == raw
        assert elem["blob_format"] == ".fits"
        assert elem["blob_size"] == len(raw)

    def test_create_property_from_blob_message(self):
        raw = b"fits_data"
        encoded = base64.b64encode(raw).decode()
        xml = (
            f'<setBLOBVector device="CCD Simulator" name="CCD1" state="Ok">'
            f'<oneBLOB name="CCD1" size="{len(raw)}" enclen="{len(encoded)}" format=".fits">'
            f'{encoded}'
            f'</oneBLOB>'
            f'</setBLOBVector>'
        ).encode()
        msg = self.parser.parse_message(xml)
        prop = IndiXmlParser.create_property_from_message(msg)
        assert prop is not None
        assert prop.type == IndiPropertyType.BLOB
        elem = prop.elements["CCD1"]
        assert elem.value == raw
        assert elem.blob_format == ".fits"
        assert elem.blob_size == len(raw)


# ---------------------------------------------------------------------------
# IPropertyElement BLOB accessors
# ---------------------------------------------------------------------------

class TestBlobElementAccessors:

    def test_getblobdata_returns_bytes(self):
        raw = b"\x00\x01\x02"
        elem = IPropertyElement(name="CCD1", value=raw, type=IndiPropertyType.BLOB,
                                blob_format=".fits", blob_size=len(raw))
        assert elem.getblobdata() == raw

    def test_getblobdata_empty_string_returns_empty_bytes(self):
        elem = IPropertyElement(name="CCD1", value="", type=IndiPropertyType.BLOB)
        assert elem.getblobdata() == b""

    def test_getbloblen_from_blob_size(self):
        raw = b"\x00\x01\x02"
        elem = IPropertyElement(name="CCD1", value=raw, type=IndiPropertyType.BLOB,
                                blob_size=99)
        assert elem.getbloblen() == 99  # uses blob_size attribute

    def test_getbloblen_from_data_when_size_zero(self):
        raw = b"\x00\x01\x02"
        elem = IPropertyElement(name="CCD1", value=raw, type=IndiPropertyType.BLOB,
                                blob_size=0)
        assert elem.getbloblen() == 3

    def test_getblobformat(self):
        elem = IPropertyElement(name="CCD1", value=b"", type=IndiPropertyType.BLOB,
                                blob_format=".cr2")
        assert elem.getblobformat() == ".cr2"


# ---------------------------------------------------------------------------
# newBLOB callback
# ---------------------------------------------------------------------------

class TestNewBLOBCallback:

    def test_new_blob_fires_on_set_blob(self):
        client = _make_client()
        received = []
        client.newBLOB = lambda p: received.append(p)

        raw = b"fits"
        encoded = base64.b64encode(raw).decode()
        xml = (
            f'<setBLOBVector device="CCD Simulator" name="CCD1" state="Ok">'
            f'<oneBLOB name="CCD1" size="{len(raw)}" enclen="{len(encoded)}" format=".fits">'
            f'{encoded}'
            f'</oneBLOB>'
            f'</setBLOBVector>'
        ).encode()

        msg = client._parser.parse_message(xml)
        client._handle_set_blob(msg)

        assert len(received) == 1
        prop = received[0]
        assert prop.name == "CCD1"
        assert prop.type == IndiPropertyType.BLOB
        assert prop.elements["CCD1"].getblobdata() == raw

    def test_new_blob_not_fired_for_number_update(self):
        client = _make_client()
        blob_received = []
        client.newBLOB = lambda p: blob_received.append(p)

        xml = (
            b'<setNumberVector device="Telescope" name="RADEC" state="Ok">'
            b'<oneNumber name="RA">12.5</oneNumber>'
            b'</setNumberVector>'
        )
        client._devices["Telescope"] = IDevice(name="Telescope")
        client._state.add_device("Telescope")
        client._state.add_property("Telescope", "RADEC")

        msg = client._parser.parse_message(xml)
        client._handle_set_property(msg)

        assert blob_received == []

    def test_def_blob_fires_new_property(self):
        client = _make_client()
        new_props = []
        client.newProperty = lambda p: new_props.append(p)

        xml = (
            b'<defBLOBVector device="CCD Simulator" name="CCD1" '
            b'state="Idle" perm="ro">'
            b'<defBLOB name="CCD1" label="Image"/>'
            b'</defBLOBVector>'
        )
        msg = client._parser.parse_message(xml)
        client._handle_def_property(msg)

        assert len(new_props) == 1
        assert new_props[0].name == "CCD1"
        assert new_props[0].type == IndiPropertyType.BLOB
