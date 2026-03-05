"""Pure Python INDI client implementation.

Orchestrates transport, parser, and state tracking layers to provide
the same interface as PyIndi.BaseClient-based IndiClient.
"""

import base64
import logging
import time
import threading
import xml.etree.ElementTree as ET
from typing import Optional, Callable, Dict

from .transport import IndiTransport
from .parser import IndiXmlParser
from .state import KnownState, ChangeType
from .properties import IDevice, IProperty
from .constants import IndiMessageType, INDI_HOST_DEFAULT, INDI_PORT_DEFAULT, BLOBHandling
from .errors import IndiConnectionError, IndiDisconnectedError

logger = logging.getLogger(__name__)


class PurePythonIndiClient:
    """Pure Python INDI client without libindi or pyindi-client dependencies.

    Maintains the same interface as the original PyIndi.BaseClient-based IndiClient
    to ensure backward compatibility with existing code.

    All callbacks are invoked from the reader thread context.
    Callbacks should be quick; long-running operations should be deferred.
    """

    def __init__(self, host: str = INDI_HOST_DEFAULT, port: int = INDI_PORT_DEFAULT, state_manager=None):
        """Initialize INDI client.

        Args:
            host: INDI server hostname (default: localhost)
            port: INDI server port (default: 7624)
            state_manager: Optional DeviceStateManager for state synchronization
        """
        self.host = host
        self.port = port
        self.state_manager = state_manager
        self.logger = logger

        self._transport = IndiTransport()
        self._parser = IndiXmlParser()
        self._state = KnownState()
        self._reader_running = False
        self._devices: Dict[str, IDevice] = {}

        # Bind callbacks (override these in subclasses or set them directly)
        self.serverConnected = self._default_callback
        self.serverDisconnected = self._default_callback
        self.newDevice = self._default_callback
        self.removeDevice = self._default_callback
        self.newProperty = self._default_callback
        self.updateProperty = self._default_callback
        self.removeProperty = self._default_callback
        self.newMessage = self._default_callback
        self.newUniversalMessage = self._default_callback
        self.newBLOB = self._default_callback

    def setServer(self, host: str, port: int) -> None:
        """Set INDI server host and port."""
        self.host = host
        self.port = port

    def getHost(self) -> str:
        """Get INDI server host."""
        return self.host

    def getPort(self) -> int:
        """Get INDI server port."""
        return self.port

    def connectServer(self) -> None:
        """Connect to INDI server and start listening for messages."""
        try:
            self._transport.connect(self.host, self.port)
            self._reader_running = True
            self._start_message_loop()
            self.serverConnected()

        except IndiConnectionError as e:
            self.logger.error(f"Failed to connect: {e}")
            self.serverDisconnected(1)
            raise

    def disconnectServer(self) -> None:
        """Disconnect from INDI server."""
        self._reader_running = False
        self._transport.disconnect()
        self.serverDisconnected(0)

    def watchDevice(self, device: str = "") -> None:
        """Watch a device for updates (or all devices if device is empty)."""
        if not self._transport.is_connected():
            self.logger.warning("Not connected to INDI server")
            return

        # Send getProperties command to INDI server
        if device:
            cmd = f'<getProperties version="1.7" device="{device}"/>'
        else:
            cmd = '<getProperties version="1.7"/>'

        try:
            self._transport.send_message(cmd)
        except Exception as e:
            self.logger.error(f"Failed to watch device: {e}")

    def watchProperty(self, device: str, property_name: str) -> None:
        """Watch a specific property on a device for updates."""
        if not self._transport.is_connected():
            self.logger.warning("Not connected to INDI server")
            return
        cmd = f'<getProperties version="1.7" device="{device}" name="{property_name}"/>'
        try:
            self._transport.send_message(cmd)
        except Exception as e:
            self.logger.error(f"Failed to watch property: {e}")

    def isServerConnected(self) -> bool:
        """Return True if currently connected to the INDI server."""
        return self._transport.is_connected()

    def getDevices(self):
        """Get list of known devices."""
        return [device for device in self._state.get_known_devices()]

    def getDevice(self, name: str) -> Optional[IDevice]:
        """Get a known device by name.

        Args:
            name: Device name

        Returns:
            IDevice if known, None otherwise
        """
        return self._devices.get(name)

    def connectDevice(self, device_name: str) -> None:
        """Send CONNECTION command to connect a device.

        Args:
            device_name: Name of the device to connect

        Raises:
            IndiDisconnectedError: If not connected to INDI server
        """
        self._require_connected("connectDevice")
        xml = (
            f'<newSwitchVector device="{device_name}" name="CONNECTION">'
            f'<oneSwitch name="CONNECT">On</oneSwitch>'
            f'<oneSwitch name="DISCONNECT">Off</oneSwitch>'
            f'</newSwitchVector>'
        )
        self._transport.send_message(xml)

    def disconnectDevice(self, device_name: str) -> None:
        """Send CONNECTION command to disconnect a device.

        Args:
            device_name: Name of the device to disconnect

        Raises:
            IndiDisconnectedError: If not connected to INDI server
        """
        self._require_connected("disconnectDevice")
        xml = (
            f'<newSwitchVector device="{device_name}" name="CONNECTION">'
            f'<oneSwitch name="CONNECT">Off</oneSwitch>'
            f'<oneSwitch name="DISCONNECT">On</oneSwitch>'
            f'</newSwitchVector>'
        )
        self._transport.send_message(xml)

    def sendNewNumber(self, prop_or_device, prop_name=None, elem_name=None, value=None) -> None:
        """Send a newNumberVector command to update number property values.

        Can be called in two forms:
          sendNewNumber(prop)  — full IProperty with all elements
          sendNewNumber(device_name, prop_name, elem_name, value)  — single element convenience form

        Raises:
            IndiDisconnectedError: If not connected to INDI server
        """
        self._require_connected("sendNewNumber")
        if prop_name is not None:
            device = self._devices.get(prop_or_device)
            if device:
                cached_prop = device.properties.get(prop_name)
                if cached_prop:
                    cached_elem = cached_prop.elements.get(elem_name)
                    if cached_elem:
                        cached_elem.target_value = str(value)
            xml = (
                f'<newNumberVector device="{prop_or_device}" name="{prop_name}">'
                f'<oneNumber name="{elem_name}">{value}</oneNumber>'
                f'</newNumberVector>'
            )
            self._transport.send_message(xml)
        else:
            prop = prop_or_device
            device = self._devices.get(prop.device_name)
            for elem in prop.elements.values():
                if device:
                    cached_prop = device.properties.get(prop.name)
                    if cached_prop:
                        cached_elem = cached_prop.elements.get(elem.name)
                        if cached_elem:
                            cached_elem.target_value = str(elem.value)
            parts = [f'<newNumberVector device="{prop.device_name}" name="{prop.name}">']
            for elem in prop.elements.values():
                parts.append(f'  <oneNumber name="{elem.name}">{elem.value}</oneNumber>')
            parts.append('</newNumberVector>')
            self._transport.send_message("\n".join(parts))

    def sendNewText(self, prop_or_device, prop_name=None, elem_name=None, text=None) -> None:
        """Send a newTextVector command to update text property values.

        Can be called in two forms:
          sendNewText(prop)  — full IProperty with all elements
          sendNewText(device_name, prop_name, elem_name, text)  — single element convenience form

        Raises:
            IndiDisconnectedError: If not connected to INDI server
        """
        self._require_connected("sendNewText")
        if prop_name is not None:
            device = self._devices.get(prop_or_device)
            if device:
                cached_prop = device.properties.get(prop_name)
                if cached_prop:
                    cached_elem = cached_prop.elements.get(elem_name)
                    if cached_elem:
                        cached_elem.target_value = str(text)
            xml = (
                f'<newTextVector device="{prop_or_device}" name="{prop_name}">'
                f'<oneText name="{elem_name}">{self._escape_xml(str(text))}</oneText>'
                f'</newTextVector>'
            )
            self._transport.send_message(xml)
        else:
            prop = prop_or_device
            device = self._devices.get(prop.device_name)
            for elem in prop.elements.values():
                if device:
                    cached_prop = device.properties.get(prop.name)
                    if cached_prop:
                        cached_elem = cached_prop.elements.get(elem.name)
                        if cached_elem:
                            cached_elem.target_value = str(elem.value)
            parts = [f'<newTextVector device="{prop.device_name}" name="{prop.name}">']
            for elem in prop.elements.values():
                parts.append(f'  <oneText name="{elem.name}">{self._escape_xml(elem.value)}</oneText>')
            parts.append('</newTextVector>')
            self._transport.send_message("\n".join(parts))

    def sendNewSwitch(self, prop_or_device, prop_name=None, elem_name=None) -> None:
        """Send a newSwitchVector command to update switch property values.

        Can be called in two forms:
          sendNewSwitch(prop)  — full IProperty with all elements
          sendNewSwitch(device_name, prop_name, elem_name)  — single element (sets to On)

        Raises:
            IndiDisconnectedError: If not connected to INDI server
        """
        self._require_connected("sendNewSwitch")
        if prop_name is not None:
            device = self._devices.get(prop_or_device)
            if device:
                cached_prop = device.properties.get(prop_name)
                if cached_prop:
                    cached_elem = cached_prop.elements.get(elem_name)
                    if cached_elem:
                        cached_elem.target_value = "On"
            xml = (
                f'<newSwitchVector device="{prop_or_device}" name="{prop_name}">'
                f'<oneSwitch name="{elem_name}">On</oneSwitch>'
                f'</newSwitchVector>'
            )
            self._transport.send_message(xml)
        else:
            prop = prop_or_device
            device = self._devices.get(prop.device_name)
            for elem in prop.elements.values():
                if device:
                    cached_prop = device.properties.get(prop.name)
                    if cached_prop:
                        cached_elem = cached_prop.elements.get(elem.name)
                        if cached_elem:
                            cached_elem.target_value = str(elem.value)
            parts = [f'<newSwitchVector device="{prop.device_name}" name="{prop.name}">']
            for elem in prop.elements.values():
                parts.append(f'  <oneSwitch name="{elem.name}">{elem.value}</oneSwitch>')
            parts.append('</newSwitchVector>')
            self._transport.send_message("\n".join(parts))

    def sendNewBLOB(self, prop: IProperty) -> None:
        """Send a newBLOBVector command to upload binary data.

        Each element's value should be raw bytes or a pre-encoded base64 string.
        Set elem.blob_format (e.g. ".fits") and elem.blob_size (unencoded byte count)
        before calling. blob_size is auto-computed when value is raw bytes and blob_size=0.

        Args:
            prop: IProperty of type "blob" with element values containing raw bytes
                  or pre-encoded base64 strings

        Raises:
            IndiDisconnectedError: If not connected to INDI server
        """
        self._require_connected("sendNewBLOB")
        root = ET.Element("newBLOBVector")
        root.set("device", prop.device_name)
        root.set("name", prop.name)
        for elem in prop.elements.values():
            raw = elem.value
            if isinstance(raw, (bytes, bytearray)):
                size = elem.blob_size if elem.blob_size > 0 else len(raw)
                encoded = base64.b64encode(raw).decode("ascii")
            else:
                encoded = raw
                size = elem.blob_size
            blob_elem = ET.SubElement(root, "oneBLOB")
            blob_elem.set("name", elem.name)
            blob_elem.set("size", str(size))
            blob_elem.set("format", elem.blob_format or ".fits")
            blob_elem.set("enclen", str(len(encoded)))
            blob_elem.text = encoded
        self._transport.send_message(ET.tostring(root, encoding="unicode"))

    def setBLOBMode(self, mode: str, device: str = "", property: str = "") -> None:
        """Set BLOB handling mode for a device or device/property pair.

        Args:
            mode: One of "Never", "Also", or "Only"
            device: Device name
            property: Optional property name to restrict mode to one property

        Raises:
            IndiDisconnectedError: If not connected to INDI server
            ValueError: If mode is not a valid INDI BLOB mode
        """
        self._require_connected("setBLOBMode")
        # Accept either a BLOBHandling enum or a plain string
        if isinstance(mode, BLOBHandling):
            mode_str = mode.value
        else:
            mode_str = mode
        if mode_str not in {"Never", "Also", "Only"}:
            raise ValueError(f"Invalid BLOB mode '{mode_str}'. Must be one of: Never, Also, Only")
        if property:
            xml_str = f'<enableBLOB device="{device}" name="{property}">{mode_str}</enableBLOB>'
        else:
            xml_str = f'<enableBLOB device="{device}">{mode_str}</enableBLOB>'
        self._transport.send_message(xml_str)

    def _start_message_loop(self) -> None:
        import threading
        reader_thread = threading.Thread(target=self._process_messages, daemon=True)
        reader_thread.start()

    def _process_messages(self) -> None:
        """Process incoming messages from INDI server."""
        while self._reader_running and self._transport.is_connected():
            try:
                message_bytes = self._transport.get_message(timeout=0.1)
                if not message_bytes:
                    continue

                # Parse message
                message = self._parser.parse_message(message_bytes)
                if not message:
                    continue

                # Process message
                self._handle_message(message)

            except Exception as e:
                self.logger.error(f"Error processing message: {e}")

        if self._reader_running:
            self._reader_running = False
            self.serverDisconnected(1)

    def _handle_message(self, message) -> None:
        """Handle a parsed INDI message."""
        msg_type = message.message_type

        if msg_type == IndiMessageType.message:
            self._handle_message_event(message)

        elif msg_type in (IndiMessageType.def_number, IndiMessageType.def_text,
                          IndiMessageType.def_switch, IndiMessageType.def_light,
                          IndiMessageType.def_blob):
            self._handle_def_property(message)

        elif msg_type in (IndiMessageType.set_number, IndiMessageType.set_text,
                          IndiMessageType.set_switch, IndiMessageType.set_light):
            self._handle_set_property(message)

        elif msg_type == IndiMessageType.set_blob:
            self._handle_set_blob(message)

        elif msg_type == IndiMessageType.del_property:
            self._handle_del_property(message)

        elif msg_type == IndiMessageType.del_device:
            self._handle_del_device(message)

    def _handle_message_event(self, message) -> None:
        """Handle message event from server."""
        device_name = message.device_name
        message_text = message.data.get("message", "")

        if not device_name:
            self.logger.info("[INDI message] %s", message_text)
            self.newUniversalMessage(message_text)
            return

        self.logger.info("[INDI message] %s: %s", device_name, message_text)
        device = self._devices.get(device_name)
        if device:
            device.addMessage(message_text)
            self.newMessage(device, message_text)

    def _handle_def_property(self, message) -> None:
        """Handle defNumber, defText, defSwitch, or defLight message."""
        device_name = message.device_name
        property_name = message.property_name

        # Detect if device is new
        device_change = self._state.get_device_change(message)
        if device_change == ChangeType.NEW:
            if device_name not in self._devices:
                device = self._parser.create_device_from_message(message)
                self._devices[device_name] = device
                self._state.add_device(device_name)
                self.newDevice(device)

        # Create/update property
        prop = self._parser.create_property_from_message(message)
        if not prop:
            return

        property_change = self._state.get_property_change(message, is_def_message=True)

        # Store property on device object
        device = self._devices.get(device_name)
        if device and prop:
            device.properties[property_name] = prop

        if property_change == ChangeType.NEW:
            self._state.add_property(device_name, property_name)
            self._update_state_manager(device_name, property_name, prop)
            self.newProperty(prop)

        elif property_change == ChangeType.UPDATED:
            self._update_state_manager(device_name, property_name, prop)
            self.updateProperty(prop)

    def _handle_set_property(self, message) -> None:
        """Handle setNumber, setText, setSwitch, or setLight message."""
        device_name = message.device_name
        property_name = message.property_name

        # Create property object
        prop = self._parser.create_property_from_message(message)
        if not prop:
            return

        property_change = self._state.get_property_change(message, is_def_message=False)

        if property_change == ChangeType.UPDATED:
            # Update property on device object
            device = self._devices.get(device_name)
            if device:
                device.properties[property_name] = prop
            self._update_state_manager(device_name, property_name, prop)
            self.updateProperty(prop)

    def _handle_set_blob(self, message) -> None:
        """Handle setBLOBVector message — fires newBLOB callback."""
        device_name = message.device_name
        property_name = message.property_name

        prop = self._parser.create_property_from_message(message)
        if not prop:
            return

        # Store on device
        device = self._devices.get(device_name)
        if device:
            device.properties[property_name] = prop

        self._state.add_property(device_name, property_name)
        self.newBLOB(prop)

    def _handle_del_property(self, message) -> None:
        """Handle delProperty message."""
        device_name = message.device_name
        property_name = message.property_name

        property_change = self._state.get_property_change(message)
        if property_change == ChangeType.DELETED:
            prop = IProperty(device_name=device_name, name=property_name)
            self._state.remove_property(device_name, property_name)
            self.removeProperty(prop)

    def _handle_del_device(self, message) -> None:
        """Handle delDevice message."""
        device_name = message.device_name

        if device_name in self._devices:
            device = self._devices.pop(device_name)
            self._state.remove_device(device_name)
            self.removeDevice(device)

    def _update_state_manager(self, device_name: str, property_name: str, prop: IProperty) -> None:
        """Update DeviceStateManager with property value."""
        if not self.state_manager:
            return

        # Extract value from property elements
        value = self._extract_value(prop)
        if value is not None:
            self.state_manager.update(device_name, property_name, value)

    @staticmethod
    def _extract_value(prop: IProperty):
        """Extract property value from IProperty object.

        Returns dict of element values, or None if extraction fails.
        """
        try:
            if not prop or not prop.elements:
                return None

            result = {}
            for elem_name, elem in prop.elements.items():
                result[elem_name] = elem.value

            return result if result else None

        except Exception:
            return None

    def _require_connected(self, operation: str = "send") -> None:
        """Raise IndiDisconnectedError if not connected to server."""
        if not self._transport.is_connected():
            raise IndiDisconnectedError(f"Cannot {operation}: not connected to INDI server")

    @staticmethod
    def _escape_xml(s: str) -> str:
        """Escape special XML characters in element text content."""
        s = s.replace("&", "&amp;")
        s = s.replace("<", "&lt;")
        s = s.replace(">", "&gt;")
        s = s.replace('"', "&quot;")
        s = s.replace("'", "&apos;")
        return s

    @staticmethod
    def _default_callback(*args, **kwargs) -> None:
        """Default callback that does nothing."""
        pass
