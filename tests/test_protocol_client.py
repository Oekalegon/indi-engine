"""Tests for PurePythonIndiClient (protocol layer).

Tests the protocol layer client that communicates with INDI servers
without dependencies on libindi or pyindi-client.
"""

import pytest
from unittest.mock import MagicMock, patch, call
from indi_engine.indi.protocol.client import PurePythonIndiClient
from indi_engine.indi.protocol.parser import IndiMessage
from indi_engine.indi.protocol.properties import IProperty, IPropertyElement, IDevice
from indi_engine.indi.protocol.constants import IndiMessageType, IndiPropertyType
from indi_engine.indi.protocol.state import ChangeType


class TestPurePythonIndiClientInit:
    """Tests for PurePythonIndiClient initialization."""

    def test_init_default_host_port(self):
        """Test initialization with default host and port."""
        client = PurePythonIndiClient()
        assert client.getHost() == "localhost"
        assert client.getPort() == 7624

    def test_init_custom_host_port(self):
        """Test initialization with custom host and port."""
        client = PurePythonIndiClient(host="192.168.1.100", port=9999)
        assert client.getHost() == "192.168.1.100"
        assert client.getPort() == 9999

    def test_init_with_state_manager(self):
        """Test initialization with state manager."""
        mock_mgr = MagicMock()
        client = PurePythonIndiClient(state_manager=mock_mgr)
        assert client.state_manager is mock_mgr

    def test_callbacks_are_initialized(self):
        """Test that all callbacks are initialized."""
        client = PurePythonIndiClient()
        assert hasattr(client, "serverConnected")
        assert hasattr(client, "serverDisconnected")
        assert hasattr(client, "newDevice")
        assert hasattr(client, "removeDevice")
        assert hasattr(client, "newProperty")
        assert hasattr(client, "updateProperty")
        assert hasattr(client, "removeProperty")
        assert hasattr(client, "newMessage")


class TestSetServer:
    """Tests for setServer method."""

    def test_set_server(self):
        """Test setting server host and port."""
        client = PurePythonIndiClient()
        client.setServer("newhost.com", 8888)
        assert client.getHost() == "newhost.com"
        assert client.getPort() == 8888


class TestWatchDevice:
    """Tests for watchDevice method."""

    def test_watch_all_devices(self):
        """Test watching all devices."""
        client = PurePythonIndiClient()
        client._transport = MagicMock()
        client._transport.is_connected.return_value = True

        client.watchDevice()
        
        client._transport.send_message.assert_called_once_with(
            '<getProperties version="1.7"/>'
        )

    def test_watch_specific_device(self):
        """Test watching a specific device."""
        client = PurePythonIndiClient()
        client._transport = MagicMock()
        client._transport.is_connected.return_value = True

        client.watchDevice("Telescope")
        
        client._transport.send_message.assert_called_once_with(
            '<getProperties version="1.7" device="Telescope"/>'
        )

    def test_watch_device_when_disconnected(self):
        """Test watching device when not connected."""
        client = PurePythonIndiClient()
        client._transport = MagicMock()
        client._transport.is_connected.return_value = False

        # Should not raise, just log warning
        client.watchDevice("Telescope")
        client._transport.send_message.assert_not_called()


class TestGetDevices:
    """Tests for getDevices method."""

    def test_get_devices_empty(self):
        """Test getting devices when none are known."""
        client = PurePythonIndiClient()
        devices = client.getDevices()
        assert devices == []

    def test_get_devices_returns_known(self):
        """Test getting known devices."""
        client = PurePythonIndiClient()
        client._state.add_device("Telescope")
        client._state.add_device("CCD")

        devices = client.getDevices()
        assert "Telescope" in devices
        assert "CCD" in devices


class TestExtractValue:
    """Tests for _extract_value helper method."""

    def test_extract_from_number_property(self):
        """Test extracting value from number property."""
        elem1 = IPropertyElement(name="RA", value="12.5")
        elem2 = IPropertyElement(name="DEC", value="45.0")
        prop = IProperty(device_name="Telescope", name="RADEC", type=IndiPropertyType.NUMBER)
        prop.elements = {"RA": elem1, "DEC": elem2}

        result = PurePythonIndiClient._extract_value(prop)
        assert result == {"RA": "12.5", "DEC": "45.0"}

    def test_extract_from_text_property(self):
        """Test extracting value from text property."""
        elem = IPropertyElement(name="LABEL", value="Telescope 1")
        prop = IProperty(device_name="Telescope", name="INFO", type=IndiPropertyType.TEXT)
        prop.elements = {"LABEL": elem}

        result = PurePythonIndiClient._extract_value(prop)
        assert result == {"LABEL": "Telescope 1"}

    def test_extract_from_switch_property(self):
        """Test extracting value from switch property."""
        elem = IPropertyElement(name="ON", value="On")
        prop = IProperty(device_name="Telescope", name="POWER", type=IndiPropertyType.SWITCH)
        prop.elements = {"ON": elem}

        result = PurePythonIndiClient._extract_value(prop)
        assert result == {"ON": "On"}

    def test_extract_from_empty_property(self):
        """Test extracting value from property with no elements."""
        prop = IProperty(device_name="Telescope", name="INFO", type=IndiPropertyType.NUMBER)
        result = PurePythonIndiClient._extract_value(prop)
        assert result is None

    def test_extract_from_none_property(self):
        """Test extracting value from None."""
        result = PurePythonIndiClient._extract_value(None)
        assert result is None

    def test_extract_handles_exception(self):
        """Test that extraction handles exceptions gracefully."""
        prop = MagicMock()
        prop.elements = {}
        # Simulate an exception during attribute access
        type(prop).elements = property(lambda self: (_ for _ in ()).throw(RuntimeError("boom")))

        result = PurePythonIndiClient._extract_value(prop)
        assert result is None


class TestHandleDefProperty:
    """Tests for _handle_def_property method."""

    def test_new_device_callback(self):
        """Test that newDevice callback is invoked for new devices."""
        client = PurePythonIndiClient()
        client.newDevice = MagicMock()

        # Create a def property message for a new device
        message = IndiMessage(
            message_type=IndiMessageType.def_number,
            device_name="Telescope",
            property_name="RADEC",
            data={"type": "number", "state": "Ok", "perm": "rw", "elements": {}}
        )

        client._handle_def_property(message)

        # Should have created device and called callback
        assert "Telescope" in client._devices
        client.newDevice.assert_called_once()

    def test_new_property_callback(self):
        """Test that newProperty callback is invoked for new properties."""
        client = PurePythonIndiClient()
        client.newProperty = MagicMock()
        client._state.add_device("Telescope")

        message = IndiMessage(
            message_type=IndiMessageType.def_number,
            device_name="Telescope",
            property_name="RADEC",
            data={
                "type": "number",
                "state": "Ok",
                "perm": "rw",
                "elements": {"RA": {"name": "RA", "value": "0"}}
            }
        )

        client._handle_def_property(message)
        client.newProperty.assert_called_once()

    def test_update_property_callback(self):
        """Test that updateProperty callback is invoked for property updates."""
        client = PurePythonIndiClient()
        client.updateProperty = MagicMock()
        client._state.add_device("Telescope")
        client._state.add_property("Telescope", "RADEC")

        message = IndiMessage(
            message_type=IndiMessageType.def_number,
            device_name="Telescope",
            property_name="RADEC",
            data={
                "type": "number",
                "state": "Ok",
                "perm": "rw",
                "elements": {"RA": {"name": "RA", "value": "45"}}
            }
        )

        client._handle_def_property(message)
        client.updateProperty.assert_called_once()


class TestHandleSetProperty:
    """Tests for _handle_set_property method."""

    def test_set_property_updates_property(self):
        """Test that set property message updates existing property."""
        client = PurePythonIndiClient()
        client.updateProperty = MagicMock()
        client._state.add_device("Telescope")
        client._state.add_property("Telescope", "RADEC")

        message = IndiMessage(
            message_type=IndiMessageType.set_number,
            device_name="Telescope",
            property_name="RADEC",
            data={
                "type": "number",
                "state": "Busy",
                "perm": "rw",
                "elements": {"RA": {"name": "RA", "value": "90"}}
            }
        )

        client._handle_set_property(message)
        client.updateProperty.assert_called_once()

    def test_set_property_unknown_property_doesnt_callback(self):
        """Test that set message for unknown property doesn't callback."""
        client = PurePythonIndiClient()
        client.updateProperty = MagicMock()

        message = IndiMessage(
            message_type=IndiMessageType.set_number,
            device_name="Unknown",
            property_name="Unknown",
            data={"type": "number", "state": "Ok", "perm": "rw", "elements": {}}
        )

        client._handle_set_property(message)
        client.updateProperty.assert_not_called()


class TestHandleDelProperty:
    """Tests for _handle_del_property method."""

    def test_del_property_callback(self):
        """Test that removeProperty callback is invoked."""
        client = PurePythonIndiClient()
        client.removeProperty = MagicMock()
        client._state.add_device("Telescope")
        client._state.add_property("Telescope", "RADEC")

        message = IndiMessage(
            message_type=IndiMessageType.del_property,
            device_name="Telescope",
            property_name="RADEC",
            data={}
        )

        client._handle_del_property(message)
        client.removeProperty.assert_called_once()
        assert not client._state.is_property_known("Telescope", "RADEC")

    def test_del_unknown_property_doesnt_callback(self):
        """Test that deleting unknown property doesn't callback."""
        client = PurePythonIndiClient()
        client.removeProperty = MagicMock()

        message = IndiMessage(
            message_type=IndiMessageType.del_property,
            device_name="Unknown",
            property_name="Unknown",
            data={}
        )

        client._handle_del_property(message)
        client.removeProperty.assert_not_called()


class TestHandleDelDevice:
    """Tests for _handle_del_device method."""

    def test_del_device_callback(self):
        """Test that removeDevice callback is invoked."""
        client = PurePythonIndiClient()
        client.removeDevice = MagicMock()
        
        # Add device to internal state
        device = IDevice(name="Telescope")
        client._devices["Telescope"] = device
        client._state.add_device("Telescope")

        message = IndiMessage(
            message_type=IndiMessageType.del_device,
            device_name="Telescope",
            property_name="",
            data={}
        )

        client._handle_del_device(message)
        client.removeDevice.assert_called_once()
        assert "Telescope" not in client._devices

    def test_del_unknown_device_doesnt_callback(self):
        """Test that deleting unknown device doesn't callback."""
        client = PurePythonIndiClient()
        client.removeDevice = MagicMock()

        message = IndiMessage(
            message_type=IndiMessageType.del_device,
            device_name="Unknown",
            property_name="",
            data={}
        )

        client._handle_del_device(message)
        client.removeDevice.assert_not_called()


class TestHandleMessageEvent:
    """Tests for _handle_message_event method."""

    def test_message_event_callback(self):
        """Test that newMessage callback is invoked."""
        client = PurePythonIndiClient()
        client.newMessage = MagicMock()

        # Add device to internal state
        device = IDevice(name="Telescope")
        client._devices["Telescope"] = device

        message = IndiMessage(
            message_type=IndiMessageType.message,
            device_name="Telescope",
            property_name="",
            data={"message": "Device ready"}
        )

        client._handle_message_event(message)
        client.newMessage.assert_called_once()
        # Check that message was added to device
        assert "Device ready" in device.messages

    def test_message_from_unknown_device(self):
        """Test message from unknown device is ignored."""
        client = PurePythonIndiClient()
        client.newMessage = MagicMock()

        message = IndiMessage(
            message_type=IndiMessageType.message,
            device_name="Unknown",
            property_name="",
            data={"message": "Some message"}
        )

        client._handle_message_event(message)
        client.newMessage.assert_not_called()


class TestUpdateStateManager:
    """Tests for _update_state_manager method."""

    def test_update_state_manager_called(self):
        """Test that state manager is updated with property values."""
        mock_mgr = MagicMock()
        client = PurePythonIndiClient(state_manager=mock_mgr)

        elem = IPropertyElement(name="RA", value="12.5")
        prop = IProperty(device_name="Telescope", name="RADEC", type=IndiPropertyType.NUMBER)
        prop.elements = {"RA": elem}

        client._update_state_manager("Telescope", "RADEC", prop)
        mock_mgr.update.assert_called_once_with("Telescope", "RADEC", {"RA": "12.5"})

    def test_update_without_state_manager(self):
        """Test that update without state manager doesn't raise."""
        client = PurePythonIndiClient()
        elem = IPropertyElement(name="RA", value="12.5")
        prop = IProperty(device_name="Telescope", name="RADEC", type=IndiPropertyType.NUMBER)
        prop.elements = {"RA": elem}

        # Should not raise
        client._update_state_manager("Telescope", "RADEC", prop)

    def test_update_with_none_value(self):
        """Test update when property value is None."""
        mock_mgr = MagicMock()
        client = PurePythonIndiClient(state_manager=mock_mgr)

        prop = IProperty(device_name="Telescope", name="RADEC", type=IndiPropertyType.NUMBER)
        # Empty elements dict will result in None value

        client._update_state_manager("Telescope", "RADEC", prop)
        mock_mgr.update.assert_not_called()


class TestDefaultCallback:
    """Tests for _default_callback method."""

    def test_default_callback_does_nothing(self):
        """Test that default callback doesn't raise."""
        client = PurePythonIndiClient()
        # Should not raise with any arguments
        client._default_callback()
        client._default_callback("arg1", "arg2", kwarg1="value")
