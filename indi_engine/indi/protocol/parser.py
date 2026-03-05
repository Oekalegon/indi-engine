"""INDI XML protocol message parser.

Parses raw INDI XML messages from the server and extracts structured data.
Handles all INDI message types with graceful error handling.
"""

import base64
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional, Any, Dict, List, Type, TypeVar
from dataclasses import dataclass, field
import logging

from .constants import IndiMessageType, MESSAGE_TYPE_MAP, IndiPropertyType, IndiPropertyState, IndiPropertyPerm, IndiSwitchRule
from .errors import IndiProtocolError
from .properties import IProperty, IPropertyElement, IDevice

logger = logging.getLogger(__name__)

E = TypeVar("E")


def _parse_enum(enum_cls: Type[E], value: str, default: E) -> E:
    """Convert a string to an enum value, returning default on unknown values."""
    try:
        return enum_cls(value)
    except ValueError:
        return default


@dataclass
class IndiMessage:
    """Represents a parsed INDI XML message."""
    message_type: IndiMessageType
    device_name: str = ""
    property_name: str = ""
    timestamp: Optional[datetime] = None
    data: Dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return f"IndiMessage({self.message_type.name}, device={self.device_name}, property={self.property_name})"


class IndiXmlParser:
    """Parses INDI XML protocol messages.

    The INDI protocol uses XML to communicate device/property/element structure.
    This parser converts raw XML bytes into structured message objects.
    """

    def __init__(self):
        self.logger = logger

    def parse_message(self, xml_bytes: bytes) -> Optional[IndiMessage]:
        """Parse a single INDI XML message.

        Args:
            xml_bytes: Raw XML bytes from INDI server

        Returns:
            IndiMessage if parsing succeeds, None if message is invalid/empty

        Raises:
            IndiProtocolError: If XML is malformed
        """
        try:
            root = ET.fromstring(xml_bytes)
        except ET.ParseError as e:
            self.logger.warning(f"Failed to parse XML message: {e}")
            return None

        tag = root.tag
        message_type = MESSAGE_TYPE_MAP.get(tag, IndiMessageType.unknown)

        if message_type == IndiMessageType.unknown:
            self.logger.debug(f"Unknown INDI message type: {tag}")
            return None

        # Parse common attributes
        device_name = root.get("device", "")
        property_name = root.get("name", "")
        ts_str = root.get("timestamp", "")
        timestamp = datetime.fromisoformat(ts_str).replace(tzinfo=timezone.utc) if ts_str else None

        message = IndiMessage(
            message_type=message_type,
            device_name=device_name,
            property_name=property_name,
            timestamp=timestamp,
        )

        # Parse message-specific data
        if message_type == IndiMessageType.message:
            message.data["message"] = root.get("message", "")

        elif message_type == IndiMessageType.def_number:
            self._parse_number_property(root, message, elem_tag="defNumber")

        elif message_type == IndiMessageType.set_number:
            self._parse_number_property(root, message, elem_tag="oneNumber")

        elif message_type == IndiMessageType.def_text:
            self._parse_text_property(root, message, elem_tag="defText")

        elif message_type == IndiMessageType.set_text:
            self._parse_text_property(root, message, elem_tag="oneText")

        elif message_type == IndiMessageType.def_switch:
            self._parse_switch_property(root, message, elem_tag="defSwitch")

        elif message_type == IndiMessageType.set_switch:
            self._parse_switch_property(root, message, elem_tag="oneSwitch")

        elif message_type == IndiMessageType.def_light:
            self._parse_light_property(root, message, elem_tag="defLight")

        elif message_type == IndiMessageType.set_light:
            self._parse_light_property(root, message, elem_tag="oneLight")

        elif message_type == IndiMessageType.def_blob:
            self._parse_blob_property(root, message, elem_tag="defBLOB")

        elif message_type == IndiMessageType.set_blob:
            self._parse_blob_property(root, message, elem_tag="oneBLOB")

        elif message_type == IndiMessageType.del_property:
            message.data["property"] = property_name

        elif message_type == IndiMessageType.del_device:
            message.data["device"] = device_name

        return message

    def _parse_number_property(self, root: ET.Element, message: IndiMessage, elem_tag: str = "oneNumber") -> None:
        """Parse defNumberVector or setNumberVector message."""
        message.data["type"] = "number"
        message.data["state"] = root.get("state", "Idle")
        message.data["perm"] = root.get("perm", "rw")
        message.data["label"] = root.get("label", "")
        message.data["group"] = root.get("group", "")
        message.data["elements"] = {}

        for elem in root.findall(elem_tag):
            name = elem.get("name", "")
            value_str = elem.text or "0"
            element = {
                "name": name,
                "label": elem.get("label", ""),
                "value": value_str,
                "min": elem.get("min", ""),
                "max": elem.get("max", ""),
                "step": elem.get("step", ""),
                "format": elem.get("format", ""),
            }
            message.data["elements"][name] = element

    def _parse_text_property(self, root: ET.Element, message: IndiMessage, elem_tag: str = "oneText") -> None:
        """Parse defTextVector or setTextVector message."""
        message.data["type"] = "text"
        message.data["state"] = root.get("state", "Idle")
        message.data["perm"] = root.get("perm", "rw")
        message.data["label"] = root.get("label", "")
        message.data["group"] = root.get("group", "")
        message.data["elements"] = {}

        for elem in root.findall(elem_tag):
            name = elem.get("name", "")
            value = elem.text or ""
            element = {
                "name": name,
                "label": elem.get("label", ""),
                "value": value,
            }
            message.data["elements"][name] = element

    def _parse_switch_property(self, root: ET.Element, message: IndiMessage, elem_tag: str = "oneSwitch") -> None:
        """Parse defSwitchVector or setSwitchVector message."""
        message.data["type"] = "switch"
        message.data["state"] = root.get("state", "Idle")
        message.data["perm"] = root.get("perm", "rw")
        message.data["rule"] = root.get("rule", "AnyOfMany")  # OneOfMany, AtMostOne, AnyOfMany
        message.data["label"] = root.get("label", "")
        message.data["group"] = root.get("group", "")
        message.data["elements"] = {}

        for elem in root.findall(elem_tag):
            name = elem.get("name", "")
            value = elem.text or "Off"
            element = {
                "name": name,
                "label": elem.get("label", ""),
                "value": value,  # "On" or "Off"
            }
            message.data["elements"][name] = element

    def _parse_light_property(self, root: ET.Element, message: IndiMessage, elem_tag: str = "oneLight") -> None:
        """Parse defLightVector or setLightVector message."""
        message.data["type"] = "light"
        message.data["state"] = root.get("state", "Idle")
        message.data["label"] = root.get("label", "")
        message.data["group"] = root.get("group", "")
        message.data["elements"] = {}

        for elem in root.findall(elem_tag):
            name = elem.get("name", "")
            value = elem.text or "Idle"
            element = {
                "name": name,
                "label": elem.get("label", ""),
                "value": value,  # Idle, Ok, Busy, Alert
            }
            message.data["elements"][name] = element

    def _parse_blob_property(self, root: ET.Element, message: IndiMessage, elem_tag: str = "oneBLOB") -> None:
        """Parse defBLOBVector or setBLOBVector message.

        For defBLOB elements (definitions), value is empty bytes.
        For oneBLOB elements (data), value is the decoded bytes.
        """
        message.data["type"] = "blob"
        message.data["state"] = root.get("state", "Idle")
        message.data["perm"] = root.get("perm", "ro")
        message.data["label"] = root.get("label", "")
        message.data["group"] = root.get("group", "")
        message.data["elements"] = {}

        for elem in root.findall(elem_tag):
            name = elem.get("name", "")
            blob_format = elem.get("format", "")
            size_str = elem.get("size", "0")
            blob_size = int(size_str) if size_str else 0

            # Decode base64 data if present (oneBLOB elements have content)
            raw_text = (elem.text or "").strip()
            if raw_text:
                try:
                    value = base64.b64decode(raw_text)
                except Exception:
                    self.logger.warning("Failed to decode BLOB data for element %s", name)
                    value = b""
            else:
                value = b""

            element = {
                "name": name,
                "label": elem.get("label", ""),
                "value": value,
                "blob_format": blob_format,
                "blob_size": blob_size,
            }
            message.data["elements"][name] = element

    @staticmethod
    def create_property_from_message(message: IndiMessage) -> Optional[IProperty]:
        """Create an IProperty object from a parsed INDI message.

        Args:
            message: IndiMessage from parse_message()

        Returns:
            IProperty object, or None if message doesn't contain property data
        """
        if not message.device_name or not message.property_name:
            return None

        prop_type  = _parse_enum(IndiPropertyType,  message.data.get("type",  "unknown"), IndiPropertyType.UNKNOWN)
        prop_state = _parse_enum(IndiPropertyState, message.data.get("state", "Idle"),    IndiPropertyState.IDLE)
        prop_perm  = _parse_enum(IndiPropertyPerm,  message.data.get("perm",  "rw"),      IndiPropertyPerm.RW)
        prop_rule  = _parse_enum(IndiSwitchRule,    message.data.get("rule",  "Unknown"), IndiSwitchRule.UNKNOWN)
        elem_state = _parse_enum(IndiPropertyState, message.data.get("state", "Idle"),    IndiPropertyState.IDLE)

        prop = IProperty(
            device_name=message.device_name,
            name=message.property_name,
            type=prop_type,
            state=prop_state,
            perm=prop_perm,
            timestamp=message.timestamp,
            label=message.data.get("label", ""),
            group=message.data.get("group", ""),
            rule=prop_rule,
        )

        # Create elements
        elements_data = message.data.get("elements", {})
        for elem_name, elem_data in elements_data.items():
            element = IPropertyElement(
                name=elem_name,
                value=elem_data.get("value", ""),
                state=elem_state,
                type=prop_type,
                label=elem_data.get("label", ""),
                format=elem_data.get("format", ""),
            )
            if prop_type == IndiPropertyType.NUMBER:
                min_s = elem_data.get("min", "")
                max_s = elem_data.get("max", "")
                step_s = elem_data.get("step", "")
                element.min = float(min_s) if min_s else None
                element.max = float(max_s) if max_s else None
                element.step = float(step_s) if step_s else None
            elif prop_type == IndiPropertyType.BLOB:
                element.blob_format = elem_data.get("blob_format", "")
                element.blob_size = elem_data.get("blob_size", 0)
            prop.elements[elem_name] = element

        return prop

    @staticmethod
    def create_device_from_message(message: IndiMessage) -> Optional[IDevice]:
        """Create an IDevice object from a device message.

        Args:
            message: IndiMessage from parse_message()

        Returns:
            IDevice object, or None if message doesn't contain device data
        """
        if not message.device_name:
            return None

        device = IDevice(name=message.device_name)
        return device
