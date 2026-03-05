"""Tests for INDI XML protocol parser integration.

Tests the parser that converts raw XML bytes into structured INDI messages
and property objects.
"""

import pytest
from datetime import datetime, timezone
from indi_engine.indi.protocol.parser import IndiXmlParser, IndiMessage
from indi_engine.indi.protocol.properties import IProperty, IPropertyElement, IDevice
from indi_engine.indi.protocol.constants import IndiMessageType, IndiPropertyType, IndiPropertyState
import xml.etree.ElementTree as ET


class TestIndiXmlParserInit:
    """Tests for IndiXmlParser initialization."""

    def test_parser_init(self):
        """Test parser initialization."""
        parser = IndiXmlParser()
        assert parser is not None


class TestParseNumberProperty:
    """Tests for parsing number properties."""

    def test_parse_def_number_message(self):
        """Test parsing defNumber message."""
        xml = b'''<defNumberVector device="Telescope" name="RADEC" state="Ok" perm="rw">
            <defNumber name="RA" min="0" max="360" step="0.1" format="%8.4f">12.5</defNumber>
            <defNumber name="DEC" min="-90" max="90" step="0.1" format="%8.4f">45.0</defNumber>
        </defNumberVector>'''

        parser = IndiXmlParser()
        message = parser.parse_message(xml)

        assert message is not None
        assert message.message_type == IndiMessageType.def_number
        assert message.device_name == "Telescope"
        assert message.property_name == "RADEC"
        assert message.data["type"] == "number"
        assert message.data["state"] == "Ok"
        assert message.data["perm"] == "rw"
        assert "RA" in message.data["elements"]
        assert "DEC" in message.data["elements"]

    def test_create_property_from_number_message(self):
        """Test creating IProperty from number message."""
        xml = b'''<defNumberVector device="Telescope" name="RADEC" state="Ok">
            <defNumber name="RA">12.5</defNumber>
        </defNumberVector>'''

        parser = IndiXmlParser()
        message = parser.parse_message(xml)
        prop = parser.create_property_from_message(message)

        assert prop is not None
        assert isinstance(prop, IProperty)
        assert prop.device_name == "Telescope"
        assert prop.name == "RADEC"
        assert prop.type == IndiPropertyType.NUMBER
        assert "RA" in prop.elements
        assert prop.elements["RA"].value == "12.5"


class TestParseTextProperty:
    """Tests for parsing text properties."""

    def test_parse_def_text_message(self):
        """Test parsing defText message."""
        xml = b'''<defTextVector device="Telescope" name="INFO" state="Ok" perm="rw">
            <defText name="LABEL">Telescope 1</defText>
        </defTextVector>'''

        parser = IndiXmlParser()
        message = parser.parse_message(xml)

        assert message is not None
        assert message.message_type == IndiMessageType.def_text
        assert message.data["type"] == "text"
        assert "LABEL" in message.data["elements"]

    def test_create_property_from_text_message(self):
        """Test creating IProperty from text message."""
        xml = b'''<defTextVector device="CCD" name="FILENAME" state="Ok">
            <defText name="FILE">image.fits</defText>
        </defTextVector>'''

        parser = IndiXmlParser()
        message = parser.parse_message(xml)
        prop = parser.create_property_from_message(message)

        assert prop.type == IndiPropertyType.TEXT
        assert prop.elements["FILE"].value == "image.fits"


class TestParseSwitchProperty:
    """Tests for parsing switch properties."""

    def test_parse_def_switch_message(self):
        """Test parsing defSwitch message."""
        xml = b'''<defSwitchVector device="Telescope" name="POWER" state="Ok" rule="AnyOfMany">
            <defSwitch name="ON">On</defSwitch>
            <defSwitch name="OFF">Off</defSwitch>
        </defSwitchVector>'''

        parser = IndiXmlParser()
        message = parser.parse_message(xml)

        assert message is not None
        assert message.message_type == IndiMessageType.def_switch
        assert message.data["type"] == "switch"
        assert message.data["rule"] == "AnyOfMany"
        assert "ON" in message.data["elements"]

    def test_create_property_from_switch_message(self):
        """Test creating IProperty from switch message."""
        xml = b'''<defSwitchVector device="Telescope" name="POWER" state="Ok">
            <defSwitch name="ON">On</defSwitch>
        </defSwitchVector>'''

        parser = IndiXmlParser()
        message = parser.parse_message(xml)
        prop = parser.create_property_from_message(message)

        assert prop.type == IndiPropertyType.SWITCH
        assert prop.elements["ON"].value == "On"


class TestParseLightProperty:
    """Tests for parsing light properties."""

    def test_parse_def_light_message(self):
        """Test parsing defLight message."""
        xml = b'''<defLightVector device="Telescope" name="STATUS" state="Ok">
            <defLight name="OK">Ok</defLight>
            <defLight name="ALERT">Idle</defLight>
        </defLightVector>'''

        parser = IndiXmlParser()
        message = parser.parse_message(xml)

        assert message is not None
        assert message.message_type == IndiMessageType.def_light
        assert message.data["type"] == "light"

    def test_create_property_from_light_message(self):
        """Test creating IProperty from light message."""
        xml = b'''<defLightVector device="Telescope" name="STATUS" state="Ok">
            <defLight name="OK">Ok</defLight>
        </defLightVector>'''

        parser = IndiXmlParser()
        message = parser.parse_message(xml)
        prop = parser.create_property_from_message(message)

        assert prop.type == IndiPropertyType.LIGHT
        assert prop.elements["OK"].value == "Ok"


class TestParseMessageEvent:
    """Tests for parsing message events."""

    def test_parse_message_event(self):
        """Test parsing message event."""
        xml = b'''<message device="Telescope" message="Device is ready"/>'''

        parser = IndiXmlParser()
        message = parser.parse_message(xml)

        assert message is not None
        assert message.message_type == IndiMessageType.message
        assert message.device_name == "Telescope"
        assert message.data["message"] == "Device is ready"


class TestParseDeleteProperty:
    """Tests for parsing property deletion."""

    def test_parse_del_property_message(self):
        """Test parsing delProperty message."""
        xml = b'''<delProperty device="Telescope" name="RADEC"/>'''

        parser = IndiXmlParser()
        message = parser.parse_message(xml)

        assert message is not None
        assert message.message_type == IndiMessageType.del_property
        assert message.device_name == "Telescope"
        assert message.property_name == "RADEC"


class TestParseDeleteDevice:
    """Tests for parsing device deletion."""

    def test_parse_del_device_message(self):
        """Test parsing delDevice message."""
        xml = b'''<delDevice device="Telescope"/>'''

        parser = IndiXmlParser()
        message = parser.parse_message(xml)

        assert message is not None
        assert message.message_type == IndiMessageType.del_device
        assert message.device_name == "Telescope"


class TestCreateDeviceFromMessage:
    """Tests for creating device objects."""

    def test_create_device(self):
        """Test creating device from message."""
        xml = b'''<defNumberVector device="Telescope" name="RADEC" state="Ok">
            <defNumber name="RA">12.5</defNumber>
        </defNumberVector>'''

        parser = IndiXmlParser()
        message = parser.parse_message(xml)
        device = parser.create_device_from_message(message)

        assert device is not None
        assert isinstance(device, IDevice)
        assert device.name == "Telescope"
        assert device.getDeviceName() == "Telescope"

    def test_create_device_from_message_without_device_name(self):
        """Test creating device from message without device name."""
        message = IndiMessage(
            message_type=IndiMessageType.message,
            device_name="",
            property_name="",
            data={}
        )

        parser = IndiXmlParser()
        device = parser.create_device_from_message(message)

        assert device is None


class TestParserErrorHandling:
    """Tests for parser error handling."""

    def test_parse_invalid_xml_returns_none(self):
        """Test that invalid XML returns None."""
        xml = b'''<invalid xml formatting>'''

        parser = IndiXmlParser()
        message = parser.parse_message(xml)

        assert message is None

    def test_parse_empty_bytes_returns_none(self):
        """Test that empty bytes returns None."""
        parser = IndiXmlParser()
        message = parser.parse_message(b"")

        assert message is None

    def test_parse_unknown_message_type_returns_none(self):
        """Test that unknown message type returns None."""
        xml = b'''<unknownVector device="Telescope" name="TEST"/>'''

        parser = IndiXmlParser()
        message = parser.parse_message(xml)

        # Unknown message type should return None
        assert message is None

    def test_parse_malformed_property_returns_none(self):
        """Test that property without required fields returns None."""
        xml = b'''<defNumberVector name="RADEC"/>'''  # Missing device

        parser = IndiXmlParser()
        message = parser.parse_message(xml)

        # Should still parse, but device_name will be empty
        assert message is not None
        assert message.device_name == ""


class TestSetNumberProperty:
    """Tests for parsing setNumber messages."""

    def test_parse_set_number_message(self):
        """Test parsing setNumber message."""
        xml = b'''<setNumberVector device="Telescope" name="RADEC" state="Busy">
            <oneNumber name="RA">45.0</oneNumber>
        </setNumberVector>'''

        parser = IndiXmlParser()
        message = parser.parse_message(xml)

        assert message is not None
        assert message.message_type == IndiMessageType.set_number
        assert message.data["state"] == "Busy"


class TestSetTextProperty:
    """Tests for parsing setText messages."""

    def test_parse_set_text_message(self):
        """Test parsing setText message."""
        xml = b'''<setTextVector device="CCD" name="FILENAME" state="Ok">
            <oneText name="FILE">image.fits</oneText>
        </setTextVector>'''

        parser = IndiXmlParser()
        message = parser.parse_message(xml)

        assert message is not None
        assert message.message_type == IndiMessageType.set_text


class TestSetSwitchProperty:
    """Tests for parsing setSwitch messages."""

    def test_parse_set_switch_message(self):
        """Test parsing setSwitch message."""
        xml = b'''<setSwitchVector device="Telescope" name="POWER" state="Ok">
            <oneSwitch name="ON">On</oneSwitch>
        </setSwitchVector>'''

        parser = IndiXmlParser()
        message = parser.parse_message(xml)

        assert message is not None
        assert message.message_type == IndiMessageType.set_switch


class TestSetLightProperty:
    """Tests for parsing setLight messages."""

    def test_parse_set_light_message(self):
        """Test parsing setLight message."""
        xml = b'''<setLightVector device="Telescope" name="STATUS" state="Ok">
            <oneLight name="OK">Ok</oneLight>
        </setLightVector>'''

        parser = IndiXmlParser()
        message = parser.parse_message(xml)

        assert message is not None
        assert message.message_type == IndiMessageType.set_light


class TestPropertyElements:
    """Tests for property element creation."""

    def test_number_element_has_format_info(self):
        """Test that number elements preserve format information."""
        xml = b'''<defNumberVector device="Telescope" name="RADEC" state="Ok">
            <defNumber name="RA" min="0" max="360" step="0.1" format="%8.4f">12.5</defNumber>
        </defNumberVector>'''

        parser = IndiXmlParser()
        message = parser.parse_message(xml)

        assert message.data["elements"]["RA"]["min"] == "0"
        assert message.data["elements"]["RA"]["max"] == "360"
        assert message.data["elements"]["RA"]["format"] == "%8.4f"

    def test_property_element_state_preserved(self):
        """Test that property state is preserved in elements."""
        xml = b'''<defNumberVector device="Telescope" name="RADEC" state="Busy">
            <defNumber name="RA">12.5</defNumber>
        </defNumberVector>'''

        parser = IndiXmlParser()
        message = parser.parse_message(xml)
        prop = parser.create_property_from_message(message)

        # Element should have property state
        assert prop.elements["RA"].state == IndiPropertyState.BUSY


class TestTimestamp:
    """Tests for timestamp handling."""

    def test_parse_message_with_timestamp(self):
        """Test parsing message with timestamp."""
        xml = b'''<defNumberVector device="Telescope" name="RADEC" 
                  state="Ok" timestamp="2024-03-04T12:34:56">
            <defNumber name="RA">12.5</defNumber>
        </defNumberVector>'''

        parser = IndiXmlParser()
        message = parser.parse_message(xml)

        assert message.timestamp == datetime(2024, 3, 4, 12, 34, 56, tzinfo=timezone.utc)

    def test_property_preserves_timestamp(self):
        """Test that timestamp is preserved in IProperty."""
        xml = b'''<defNumberVector device="Telescope" name="RADEC" 
                  state="Ok" timestamp="2024-03-04T12:34:56">
            <defNumber name="RA">12.5</defNumber>
        </defNumberVector>'''

        parser = IndiXmlParser()
        message = parser.parse_message(xml)
        prop = parser.create_property_from_message(message)

        assert prop.timestamp == datetime(2024, 3, 4, 12, 34, 56, tzinfo=timezone.utc)


class TestNumberElementMetadata:
    """Tests for number element min/max/step/format persistence."""

    def test_number_element_min_max_step_stored_as_float(self):
        xml = b'''<defNumberVector device="Telescope" name="RADEC" state="Ok">
            <defNumber name="RA" min="0" max="360" step="0.1" format="%8.4f">12.5</defNumber>
        </defNumberVector>'''

        parser = IndiXmlParser()
        prop = parser.create_property_from_message(parser.parse_message(xml))

        elem = prop.elements["RA"]
        assert elem.min == 0.0
        assert elem.max == 360.0
        assert elem.step == 0.1
        assert elem.format == "%8.4f"

    def test_number_element_getters(self):
        xml = b'''<defNumberVector device="Telescope" name="RADEC" state="Ok">
            <defNumber name="RA" min="-90" max="90" step="0.01" format="%.2f">0</defNumber>
        </defNumberVector>'''

        parser = IndiXmlParser()
        prop = parser.create_property_from_message(parser.parse_message(xml))
        elem = prop.elements["RA"]

        assert elem.getMin() == -90.0
        assert elem.getMax() == 90.0
        assert elem.getStep() == 0.01
        assert elem.getFormat() == "%.2f"

    def test_number_element_missing_attributes_are_none(self):
        xml = b'''<defNumberVector device="Telescope" name="RADEC" state="Ok">
            <defNumber name="RA">12.5</defNumber>
        </defNumberVector>'''

        parser = IndiXmlParser()
        prop = parser.create_property_from_message(parser.parse_message(xml))
        elem = prop.elements["RA"]

        assert elem.min is None
        assert elem.max is None
        assert elem.step is None

    def test_non_number_element_has_no_min_max(self):
        xml = b'''<defTextVector device="CCD" name="FILENAME" state="Ok">
            <defText name="FILE">image.fits</defText>
        </defTextVector>'''

        parser = IndiXmlParser()
        prop = parser.create_property_from_message(parser.parse_message(xml))
        elem = prop.elements["FILE"]

        assert elem.min is None
        assert elem.max is None


class TestSwitchRule:
    """Tests for switch rule persistence."""

    def test_switch_rule_one_of_many(self):
        xml = b'''<defSwitchVector device="Telescope" name="TRACK_MODE" state="Ok" rule="OneOfMany">
            <defSwitch name="TRACK_SIDEREAL">On</defSwitch>
            <defSwitch name="TRACK_LUNAR">Off</defSwitch>
        </defSwitchVector>'''

        parser = IndiXmlParser()
        prop = parser.create_property_from_message(parser.parse_message(xml))

        from indi_engine.indi.protocol.constants import IndiSwitchRule
        assert prop.rule == IndiSwitchRule.ONE_OF_MANY
        assert prop.getRuleAsString() == "OneOfMany"

    def test_switch_rule_any_of_many(self):
        xml = b'''<defSwitchVector device="Telescope" name="POWER" state="Ok" rule="AnyOfMany">
            <defSwitch name="ON">On</defSwitch>
        </defSwitchVector>'''

        parser = IndiXmlParser()
        prop = parser.create_property_from_message(parser.parse_message(xml))

        from indi_engine.indi.protocol.constants import IndiSwitchRule
        assert prop.rule == IndiSwitchRule.ANY_OF_MANY

    def test_switch_rule_at_most_one(self):
        xml = b'''<defSwitchVector device="Telescope" name="ABORT" state="Ok" rule="AtMostOne">
            <defSwitch name="ABORT">Off</defSwitch>
        </defSwitchVector>'''

        parser = IndiXmlParser()
        prop = parser.create_property_from_message(parser.parse_message(xml))

        from indi_engine.indi.protocol.constants import IndiSwitchRule
        assert prop.rule == IndiSwitchRule.AT_MOST_ONE


class TestGroupAndLabel:
    """Tests for group and label persistence."""

    def test_property_group_preserved(self):
        xml = b'''<defNumberVector device="Telescope" name="RADEC" state="Ok"
                  group="Motion Control" label="RA/DEC Coordinates">
            <defNumber name="RA">12.5</defNumber>
        </defNumberVector>'''

        parser = IndiXmlParser()
        prop = parser.create_property_from_message(parser.parse_message(xml))

        assert prop.group == "Motion Control"
        assert prop.getGroupName() == "Motion Control"

    def test_property_label_preserved(self):
        xml = b'''<defNumberVector device="Telescope" name="RADEC" state="Ok"
                  label="RA/DEC Coordinates">
            <defNumber name="RA">12.5</defNumber>
        </defNumberVector>'''

        parser = IndiXmlParser()
        prop = parser.create_property_from_message(parser.parse_message(xml))

        assert prop.label == "RA/DEC Coordinates"
        assert prop.getLabel() == "RA/DEC Coordinates"

    def test_element_label_preserved(self):
        xml = b'''<defNumberVector device="Telescope" name="RADEC" state="Ok">
            <defNumber name="RA" label="Right Ascension">12.5</defNumber>
        </defNumberVector>'''

        parser = IndiXmlParser()
        prop = parser.create_property_from_message(parser.parse_message(xml))

        assert prop.elements["RA"].label == "Right Ascension"
        assert prop.elements["RA"].getLabel() == "Right Ascension"


class TestPropertyIteration:
    """Tests for IProperty __getitem__ and __len__."""

    def test_len_returns_element_count(self):
        xml = b'''<defNumberVector device="Telescope" name="RADEC" state="Ok">
            <defNumber name="RA">12.5</defNumber>
            <defNumber name="DEC">45.0</defNumber>
        </defNumberVector>'''

        parser = IndiXmlParser()
        prop = parser.create_property_from_message(parser.parse_message(xml))

        assert len(prop) == 2

    def test_getitem_by_index(self):
        xml = b'''<defNumberVector device="Telescope" name="RADEC" state="Ok">
            <defNumber name="RA">12.5</defNumber>
            <defNumber name="DEC">45.0</defNumber>
        </defNumberVector>'''

        parser = IndiXmlParser()
        prop = parser.create_property_from_message(parser.parse_message(xml))

        assert prop[0].name == "RA"
        assert prop[1].name == "DEC"


class TestSwitchHelpers:
    """Tests for IProperty switch helper methods."""

    def _make_switch_prop(self):
        from indi_engine.indi.protocol.properties import IProperty, IPropertyElement
        from indi_engine.indi.protocol.constants import IndiPropertyType, IndiSwitchRule
        prop = IProperty(device_name="Telescope", name="TRACK_MODE",
                         type=IndiPropertyType.SWITCH, rule=IndiSwitchRule.ONE_OF_MANY)
        prop.elements["TRACK_SIDEREAL"] = IPropertyElement(name="TRACK_SIDEREAL", value="On")
        prop.elements["TRACK_LUNAR"] = IPropertyElement(name="TRACK_LUNAR", value="Off")
        prop.elements["TRACK_SOLAR"] = IPropertyElement(name="TRACK_SOLAR", value="Off")
        return prop

    def test_find_on_switch(self):
        prop = self._make_switch_prop()
        elem = prop.findOnSwitch()
        assert elem is not None
        assert elem.name == "TRACK_SIDEREAL"

    def test_find_on_switch_index(self):
        prop = self._make_switch_prop()
        assert prop.findOnSwitchIndex() == 0

    def test_find_on_switch_name(self):
        prop = self._make_switch_prop()
        assert prop.findOnSwitchName() == "TRACK_SIDEREAL"

    def test_is_switch_on_true(self):
        prop = self._make_switch_prop()
        assert prop.isSwitchOn("TRACK_SIDEREAL") is True

    def test_is_switch_on_false(self):
        prop = self._make_switch_prop()
        assert prop.isSwitchOn("TRACK_LUNAR") is False

    def test_is_switch_on_unknown_name(self):
        prop = self._make_switch_prop()
        assert prop.isSwitchOn("NONEXISTENT") is False

    def test_find_on_switch_none_when_all_off(self):
        from indi_engine.indi.protocol.properties import IProperty, IPropertyElement
        from indi_engine.indi.protocol.constants import IndiPropertyType
        prop = IProperty(device_name="Dev", name="P", type=IndiPropertyType.SWITCH)
        prop.elements["A"] = IPropertyElement(name="A", value="Off")
        assert prop.findOnSwitch() is None
        assert prop.findOnSwitchIndex() == -1
        assert prop.findOnSwitchName() == ""


class TestIDeviceIsConnected:
    """Tests for IDevice.isConnected()."""

    def test_returns_true_when_connect_is_on(self):
        from indi_engine.indi.protocol.properties import IDevice, IProperty, IPropertyElement
        from indi_engine.indi.protocol.constants import IndiPropertyType
        device = IDevice(name="Telescope")
        conn_prop = IProperty(device_name="Telescope", name="CONNECTION",
                              type=IndiPropertyType.SWITCH)
        conn_prop.elements["CONNECT"] = IPropertyElement(name="CONNECT", value="On")
        conn_prop.elements["DISCONNECT"] = IPropertyElement(name="DISCONNECT", value="Off")
        device.properties["CONNECTION"] = conn_prop
        assert device.isConnected() is True

    def test_returns_false_when_connect_is_off(self):
        from indi_engine.indi.protocol.properties import IDevice, IProperty, IPropertyElement
        from indi_engine.indi.protocol.constants import IndiPropertyType
        device = IDevice(name="Telescope")
        conn_prop = IProperty(device_name="Telescope", name="CONNECTION",
                              type=IndiPropertyType.SWITCH)
        conn_prop.elements["CONNECT"] = IPropertyElement(name="CONNECT", value="Off")
        conn_prop.elements["DISCONNECT"] = IPropertyElement(name="DISCONNECT", value="On")
        device.properties["CONNECTION"] = conn_prop
        assert device.isConnected() is False

    def test_returns_false_when_no_connection_property(self):
        from indi_engine.indi.protocol.properties import IDevice
        device = IDevice(name="Telescope")
        assert device.isConnected() is False
