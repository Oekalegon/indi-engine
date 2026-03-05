"""Tests for PurePythonIndiClient control-side (send) methods.

Tests all methods that send commands to the INDI server:
- sendNewNumber, sendNewText, sendNewSwitch, sendNewBLOB
- getDevice, setBLOBMode

Also tests IPropertyElement setter methods.
"""

import pytest
from unittest.mock import MagicMock

from indi_engine.indi.protocol.client import PurePythonIndiClient
from indi_engine.indi.protocol.properties import IProperty, IPropertyElement, IDevice
from indi_engine.indi.protocol.constants import IndiPropertyType, IndiPropertyState
from indi_engine.indi.protocol.errors import IndiDisconnectedError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client(connected: bool = True) -> PurePythonIndiClient:
    client = PurePythonIndiClient()
    client._transport = MagicMock()
    client._transport.is_connected.return_value = connected
    return client


def _make_prop(device: str, name: str, prop_type: IndiPropertyType, elements: dict) -> IProperty:
    prop = IProperty(device_name=device, name=name, type=prop_type)
    for elem_name, value in elements.items():
        prop.elements[elem_name] = IPropertyElement(name=elem_name, value=value, type=prop_type)
    return prop


# ---------------------------------------------------------------------------
# IPropertyElement setters
# ---------------------------------------------------------------------------

class TestIPropertyElementSetters:

    def test_set_value(self):
        elem = IPropertyElement(name="RA", value="0.0")
        elem.setValue("12.5")
        assert elem.value == "12.5"

    def test_set_text(self):
        elem = IPropertyElement(name="FILE", value="")
        elem.setText("image.fits")
        assert elem.value == "image.fits"

    def test_set_state(self):
        elem = IPropertyElement(name="RA", value="0.0", state=IndiPropertyState.IDLE)
        elem.setState(IndiPropertyState.OK)
        assert elem.state == IndiPropertyState.OK

    def test_set_value_get_value_roundtrip(self):
        elem = IPropertyElement(name="DEC", value="0.0")
        elem.setValue("45.0")
        assert elem.getValue() == "45.0"
        assert elem.getText() == "45.0"

    def test_blob_fields_default_to_empty(self):
        elem = IPropertyElement(name="CCD1", value="")
        assert elem.blob_format == ""
        assert elem.blob_size == 0


# ---------------------------------------------------------------------------
# sendNewNumber
# ---------------------------------------------------------------------------

class TestSendNewNumber:

    def test_sends_correct_xml(self):
        client = _make_client()
        prop = _make_prop("Telescope", "RADEC", IndiPropertyType.NUMBER, {"RA": "12.5", "DEC": "45.0"})
        client.sendNewNumber(prop)
        sent = client._transport.send_message.call_args[0][0]
        assert '<newNumberVector device="Telescope" name="RADEC">' in sent
        assert '<oneNumber name="RA">12.5</oneNumber>' in sent
        assert '<oneNumber name="DEC">45.0</oneNumber>' in sent
        assert '</newNumberVector>' in sent

    def test_raises_when_disconnected(self):
        client = _make_client(connected=False)
        prop = _make_prop("Telescope", "RADEC", IndiPropertyType.NUMBER, {"RA": "0"})
        with pytest.raises(IndiDisconnectedError):
            client.sendNewNumber(prop)

    def test_calls_transport_once(self):
        client = _make_client()
        prop = _make_prop("Telescope", "RADEC", IndiPropertyType.NUMBER, {"RA": "12.5"})
        client.sendNewNumber(prop)
        client._transport.send_message.assert_called_once()

    def test_single_element(self):
        client = _make_client()
        prop = _make_prop("Mount", "SLEW_RATE", IndiPropertyType.NUMBER, {"RATE": "3"})
        client.sendNewNumber(prop)
        sent = client._transport.send_message.call_args[0][0]
        assert '<oneNumber name="RATE">3</oneNumber>' in sent


# ---------------------------------------------------------------------------
# sendNewText
# ---------------------------------------------------------------------------

class TestSendNewText:

    def test_sends_correct_xml(self):
        client = _make_client()
        prop = _make_prop("CCD", "FILENAME", IndiPropertyType.TEXT, {"FILE": "image.fits"})
        client.sendNewText(prop)
        sent = client._transport.send_message.call_args[0][0]
        assert '<newTextVector device="CCD" name="FILENAME">' in sent
        assert '<oneText name="FILE">image.fits</oneText>' in sent
        assert '</newTextVector>' in sent

    def test_raises_when_disconnected(self):
        client = _make_client(connected=False)
        prop = _make_prop("CCD", "FILENAME", IndiPropertyType.TEXT, {"FILE": "x.fits"})
        with pytest.raises(IndiDisconnectedError):
            client.sendNewText(prop)

    def test_xml_special_chars_escaped(self):
        client = _make_client()
        prop = _make_prop("CCD", "LABEL", IndiPropertyType.TEXT, {"NAME": "foo & <bar>"})
        client.sendNewText(prop)
        sent = client._transport.send_message.call_args[0][0]
        assert "foo &amp; &lt;bar&gt;" in sent
        assert "foo & <bar>" not in sent

    def test_ampersand_escaped_before_lt(self):
        client = _make_client()
        prop = _make_prop("Dev", "P", IndiPropertyType.TEXT, {"E": "&lt;"})
        client.sendNewText(prop)
        sent = client._transport.send_message.call_args[0][0]
        assert "&amp;lt;" in sent


# ---------------------------------------------------------------------------
# sendNewSwitch
# ---------------------------------------------------------------------------

class TestSendNewSwitch:

    def test_sends_correct_xml(self):
        client = _make_client()
        prop = _make_prop("Telescope", "CONNECTION", IndiPropertyType.SWITCH,
                          {"CONNECT": "On", "DISCONNECT": "Off"})
        client.sendNewSwitch(prop)
        sent = client._transport.send_message.call_args[0][0]
        assert '<newSwitchVector device="Telescope" name="CONNECTION">' in sent
        assert '<oneSwitch name="CONNECT">On</oneSwitch>' in sent
        assert '<oneSwitch name="DISCONNECT">Off</oneSwitch>' in sent
        assert '</newSwitchVector>' in sent

    def test_raises_when_disconnected(self):
        client = _make_client(connected=False)
        prop = _make_prop("Telescope", "CONNECTION", IndiPropertyType.SWITCH, {"CONNECT": "On"})
        with pytest.raises(IndiDisconnectedError):
            client.sendNewSwitch(prop)

    def test_single_switch_element(self):
        client = _make_client()
        prop = _make_prop("Focuser", "FOCUS_ABORT_MOTION", IndiPropertyType.SWITCH, {"ABORT": "On"})
        client.sendNewSwitch(prop)
        sent = client._transport.send_message.call_args[0][0]
        assert '<oneSwitch name="ABORT">On</oneSwitch>' in sent


# ---------------------------------------------------------------------------
# sendNewBLOB
# ---------------------------------------------------------------------------

class TestSendNewBLOB:

    def test_sends_correct_xml_with_raw_bytes(self):
        import base64
        client = _make_client()
        raw_data = b"fake fits data"
        prop = IProperty(device_name="CCD", name="CCD1", type=IndiPropertyType.BLOB)
        elem = IPropertyElement(name="CCD1", value=raw_data, type=IndiPropertyType.BLOB,
                                blob_format=".fits", blob_size=len(raw_data))
        prop.elements["CCD1"] = elem
        client.sendNewBLOB(prop)
        sent = client._transport.send_message.call_args[0][0]
        expected_b64 = base64.b64encode(raw_data).decode("ascii")
        assert 'device="CCD"' in sent
        assert 'name="CCD1"' in sent
        assert f'size="{len(raw_data)}"' in sent
        assert 'format=".fits"' in sent
        assert expected_b64 in sent

    def test_raises_when_disconnected(self):
        client = _make_client(connected=False)
        prop = IProperty(device_name="CCD", name="CCD1", type=IndiPropertyType.BLOB)
        elem = IPropertyElement(name="CCD1", value=b"data", type=IndiPropertyType.BLOB, blob_format=".fits")
        prop.elements["CCD1"] = elem
        with pytest.raises(IndiDisconnectedError):
            client.sendNewBLOB(prop)

    def test_auto_computes_size_from_bytes(self):
        client = _make_client()
        raw = b"\x00\x01\x02\x03"
        prop = IProperty(device_name="CCD", name="CCD1", type=IndiPropertyType.BLOB)
        elem = IPropertyElement(name="CCD1", value=raw, type=IndiPropertyType.BLOB,
                                blob_format=".raw", blob_size=0)
        prop.elements["CCD1"] = elem
        client.sendNewBLOB(prop)
        sent = client._transport.send_message.call_args[0][0]
        assert f'size="{len(raw)}"' in sent

    def test_accepts_pre_encoded_string(self):
        import base64
        client = _make_client()
        raw = b"abc"
        pre_encoded = base64.b64encode(raw).decode("ascii")
        prop = IProperty(device_name="CCD", name="CCD1", type=IndiPropertyType.BLOB)
        elem = IPropertyElement(name="CCD1", value=pre_encoded, type=IndiPropertyType.BLOB,
                                blob_format=".fits", blob_size=len(raw))
        prop.elements["CCD1"] = elem
        client.sendNewBLOB(prop)
        sent = client._transport.send_message.call_args[0][0]
        assert pre_encoded in sent


# ---------------------------------------------------------------------------
# getDevice
# ---------------------------------------------------------------------------

class TestGetDevice:

    def test_returns_known_device(self):
        client = _make_client()
        device = IDevice(name="Telescope")
        client._devices["Telescope"] = device
        assert client.getDevice("Telescope") is device

    def test_returns_none_for_unknown_device(self):
        client = _make_client()
        assert client.getDevice("Unknown") is None

    def test_returns_none_on_empty_devices(self):
        client = _make_client()
        assert client.getDevice("Any") is None


# ---------------------------------------------------------------------------
# setBLOBMode
# ---------------------------------------------------------------------------

class TestSetBLOBMode:

    def test_sends_mode_without_property(self):
        client = _make_client()
        client.setBLOBMode("Also", device="CCD Simulator")
        client._transport.send_message.assert_called_once_with(
            '<enableBLOB device="CCD Simulator">Also</enableBLOB>'
        )

    def test_sends_mode_with_property(self):
        client = _make_client()
        client.setBLOBMode("Only", device="CCD Simulator", property="CCD1")
        client._transport.send_message.assert_called_once_with(
            '<enableBLOB device="CCD Simulator" name="CCD1">Only</enableBLOB>'
        )

    def test_sends_never_mode(self):
        client = _make_client()
        client.setBLOBMode("Never", device="CCD Simulator")
        sent = client._transport.send_message.call_args[0][0]
        assert ">Never<" in sent

    def test_raises_when_disconnected(self):
        client = _make_client(connected=False)
        with pytest.raises(IndiDisconnectedError):
            client.setBLOBMode("Also", device="CCD")

    def test_raises_on_invalid_mode(self):
        client = _make_client()
        with pytest.raises(ValueError, match="Invalid BLOB mode"):
            client.setBLOBMode("invalid", device="CCD")


# ---------------------------------------------------------------------------
# _escape_xml helper
# ---------------------------------------------------------------------------

class TestEscapeXml:

    def test_escapes_ampersand(self):
        assert PurePythonIndiClient._escape_xml("a&b") == "a&amp;b"

    def test_escapes_lt(self):
        assert PurePythonIndiClient._escape_xml("a<b") == "a&lt;b"

    def test_escapes_gt(self):
        assert PurePythonIndiClient._escape_xml("a>b") == "a&gt;b"

    def test_escapes_double_quote(self):
        assert PurePythonIndiClient._escape_xml('a"b') == "a&quot;b"

    def test_escapes_single_quote(self):
        assert PurePythonIndiClient._escape_xml("a'b") == "a&apos;b"

    def test_no_double_escape_ampersand(self):
        assert PurePythonIndiClient._escape_xml("&lt;") == "&amp;lt;"

    def test_plain_string_unchanged(self):
        assert PurePythonIndiClient._escape_xml("hello world") == "hello world"


# ---------------------------------------------------------------------------
# isServerConnected
# ---------------------------------------------------------------------------

class TestIsServerConnected:

    def test_returns_true_when_connected(self):
        client = _make_client(connected=True)
        assert client.isServerConnected() is True

    def test_returns_false_when_disconnected(self):
        client = _make_client(connected=False)
        assert client.isServerConnected() is False


# ---------------------------------------------------------------------------
# connectDevice / disconnectDevice
# ---------------------------------------------------------------------------

class TestConnectDevice:

    def test_sends_correct_xml(self):
        client = _make_client()
        client.connectDevice("Telescope Simulator")
        sent = client._transport.send_message.call_args[0][0]
        assert 'device="Telescope Simulator"' in sent
        assert 'name="CONNECTION"' in sent
        assert '<oneSwitch name="CONNECT">On</oneSwitch>' in sent
        assert '<oneSwitch name="DISCONNECT">Off</oneSwitch>' in sent

    def test_raises_when_disconnected(self):
        client = _make_client(connected=False)
        with pytest.raises(IndiDisconnectedError):
            client.connectDevice("Telescope")


class TestDisconnectDevice:

    def test_sends_correct_xml(self):
        client = _make_client()
        client.disconnectDevice("Telescope Simulator")
        sent = client._transport.send_message.call_args[0][0]
        assert 'device="Telescope Simulator"' in sent
        assert 'name="CONNECTION"' in sent
        assert '<oneSwitch name="CONNECT">Off</oneSwitch>' in sent
        assert '<oneSwitch name="DISCONNECT">On</oneSwitch>' in sent

    def test_raises_when_disconnected(self):
        client = _make_client(connected=False)
        with pytest.raises(IndiDisconnectedError):
            client.disconnectDevice("Telescope")


# ---------------------------------------------------------------------------
# sendNewNumber convenience form
# ---------------------------------------------------------------------------

class TestSendNewNumberConvenience:

    def test_sends_single_element(self):
        client = _make_client()
        client.sendNewNumber("Telescope", "EQUATORIAL_EOD_COORD", "RA", 12.5)
        sent = client._transport.send_message.call_args[0][0]
        assert 'device="Telescope"' in sent
        assert 'name="EQUATORIAL_EOD_COORD"' in sent
        assert '<oneNumber name="RA">12.5</oneNumber>' in sent

    def test_raises_when_disconnected(self):
        client = _make_client(connected=False)
        with pytest.raises(IndiDisconnectedError):
            client.sendNewNumber("Dev", "Prop", "Elem", 0.0)

    def test_full_form_still_works(self):
        client = _make_client()
        prop = _make_prop("Mount", "SLEW_RATE", IndiPropertyType.NUMBER, {"RATE": "3"})
        client.sendNewNumber(prop)
        sent = client._transport.send_message.call_args[0][0]
        assert '<oneNumber name="RATE">3</oneNumber>' in sent


# ---------------------------------------------------------------------------
# sendNewText convenience form
# ---------------------------------------------------------------------------

class TestSendNewTextConvenience:

    def test_sends_single_element(self):
        client = _make_client()
        client.sendNewText("CCD", "FILENAME", "FILE", "image.fits")
        sent = client._transport.send_message.call_args[0][0]
        assert 'device="CCD"' in sent
        assert 'name="FILENAME"' in sent
        assert '<oneText name="FILE">image.fits</oneText>' in sent

    def test_escapes_special_chars(self):
        client = _make_client()
        client.sendNewText("Dev", "Prop", "Elem", "a & b")
        sent = client._transport.send_message.call_args[0][0]
        assert "a &amp; b" in sent

    def test_raises_when_disconnected(self):
        client = _make_client(connected=False)
        with pytest.raises(IndiDisconnectedError):
            client.sendNewText("Dev", "Prop", "Elem", "val")


# ---------------------------------------------------------------------------
# sendNewSwitch convenience form
# ---------------------------------------------------------------------------

class TestSendNewSwitchConvenience:

    def test_sends_single_element_as_on(self):
        client = _make_client()
        client.sendNewSwitch("Telescope", "TRACK_MODE", "TRACK_SIDEREAL")
        sent = client._transport.send_message.call_args[0][0]
        assert 'device="Telescope"' in sent
        assert 'name="TRACK_MODE"' in sent
        assert '<oneSwitch name="TRACK_SIDEREAL">On</oneSwitch>' in sent

    def test_raises_when_disconnected(self):
        client = _make_client(connected=False)
        with pytest.raises(IndiDisconnectedError):
            client.sendNewSwitch("Dev", "Prop", "Elem")


# ---------------------------------------------------------------------------
# watchProperty
# ---------------------------------------------------------------------------

class TestWatchProperty:

    def test_sends_get_properties_with_device_and_name(self):
        client = _make_client()
        client.watchProperty("Telescope", "EQUATORIAL_EOD_COORD")
        sent = client._transport.send_message.call_args[0][0]
        assert 'device="Telescope"' in sent
        assert 'name="EQUATORIAL_EOD_COORD"' in sent
        assert "getProperties" in sent

    def test_does_not_send_when_disconnected(self):
        client = _make_client(connected=False)
        client.watchProperty("Telescope", "EQUATORIAL_EOD_COORD")
        client._transport.send_message.assert_not_called()


# ---------------------------------------------------------------------------
# newUniversalMessage
# ---------------------------------------------------------------------------

class TestNewUniversalMessage:

    def test_universal_message_fires_for_device_less_message(self):
        client = _make_client()
        received = []
        client.newUniversalMessage = lambda text: received.append(text)

        from indi_engine.indi.protocol.parser import IndiMessage
        from indi_engine.indi.protocol.constants import IndiMessageType
        msg = IndiMessage(message_type=IndiMessageType.message, device_name="", data={"message": "Server ready"})
        client._handle_message_event(msg)

        assert received == ["Server ready"]

    def test_new_message_fires_for_device_message(self):
        client = _make_client()
        from indi_engine.indi.protocol.properties import IDevice
        device = IDevice(name="Telescope")
        client._devices["Telescope"] = device

        received = []
        client.newMessage = lambda d, m: received.append((d.getDeviceName(), m))

        from indi_engine.indi.protocol.parser import IndiMessage
        from indi_engine.indi.protocol.constants import IndiMessageType
        msg = IndiMessage(message_type=IndiMessageType.message, device_name="Telescope", data={"message": "Slewing"})
        client._handle_message_event(msg)

        assert received == [("Telescope", "Slewing")]

    def test_universal_message_not_called_for_device_message(self):
        client = _make_client()
        universal_called = []
        client.newUniversalMessage = lambda text: universal_called.append(text)
        from indi_engine.indi.protocol.properties import IDevice
        client._devices["Telescope"] = IDevice(name="Telescope")

        from indi_engine.indi.protocol.parser import IndiMessage
        from indi_engine.indi.protocol.constants import IndiMessageType
        msg = IndiMessage(message_type=IndiMessageType.message, device_name="Telescope", data={"message": "Hi"})
        client._handle_message_event(msg)

        assert universal_called == []


# ---------------------------------------------------------------------------
# isNameMatch / isValid / IDevice.isNameMatch
# ---------------------------------------------------------------------------

class TestIsNameMatch:

    def test_iproperty_name_matches(self):
        prop = IProperty(device_name="Dev", name="FOCUS_ABS_POSITION", type=IndiPropertyType.NUMBER)
        assert prop.isNameMatch("FOCUS_ABS_POSITION") is True
        assert prop.isNameMatch("OTHER") is False

    def test_idevice_name_matches(self):
        from indi_engine.indi.protocol.properties import IDevice
        device = IDevice(name="Telescope Simulator")
        assert device.isNameMatch("Telescope Simulator") is True
        assert device.isNameMatch("CCD") is False


class TestIsValid:

    def test_valid_property_returns_true(self):
        prop = IProperty(device_name="Dev", name="EXPOSURE", type=IndiPropertyType.NUMBER)
        assert prop.isValid() is True

    def test_missing_device_name_returns_false(self):
        prop = IProperty(device_name="", name="EXPOSURE", type=IndiPropertyType.NUMBER)
        assert prop.isValid() is False

    def test_missing_name_returns_false(self):
        prop = IProperty(device_name="Dev", name="", type=IndiPropertyType.NUMBER)
        assert prop.isValid() is False

    def test_unknown_type_returns_false(self):
        from indi_engine.indi.protocol.constants import IndiPropertyType
        prop = IProperty(device_name="Dev", name="EXPOSURE", type=IndiPropertyType.UNKNOWN)
        assert prop.isValid() is False
