"""INDI device and property state tracking.

Maintains snapshots of known devices/properties and detects changes
to determine what callbacks to invoke.
"""

from typing import Optional, Set, Tuple, Dict, List
from enum import Enum
import logging

from .parser import IndiMessage, IndiXmlParser
from .properties import IDevice, IProperty

logger = logging.getLogger(__name__)


class ChangeType(Enum):
    """Type of change detected."""
    NEW = "new"
    UPDATED = "updated"
    DELETED = "deleted"


class KnownState:
    """Tracks known INDI devices and properties.

    Compares incoming messages against the snapshot to detect:
    - NEW devices and properties
    - UPDATED properties
    - DELETED devices and properties

    This enables accurate callback invocation.
    """

    def __init__(self):
        self.known_devices: Set[str] = set()
        self.known_properties: Dict[str, Set[str]] = {}  # device -> {property names}
        self.logger = logger
        self.parser = IndiXmlParser()

    def get_device_change(self, message: IndiMessage) -> Optional[ChangeType]:
        """Detect if a device is new or already known.

        Args:
            message: Parsed INDI message

        Returns:
            ChangeType.NEW if device is new, None if known
        """
        device_name = message.device_name
        if not device_name:
            return None

        if device_name in self.known_devices:
            return None

        return ChangeType.NEW

    def get_property_change(self, message: IndiMessage, is_def_message: bool = False) -> Optional[ChangeType]:
        """Detect if a property is new, updated, or deleted.

        Args:
            message: Parsed INDI message
            is_def_message: True if this is a def* message (new or re-definition)

        Returns:
            ChangeType.NEW if property is new
            ChangeType.UPDATED if property exists (set* message)
            ChangeType.DELETED if property is being deleted
            None if property is unknown
        """
        device_name = message.device_name
        property_name = message.property_name

        if not device_name or not property_name:
            return None

        # delProperty messages indicate deletion
        if message.message_type.name == "del_property":
            if device_name in self.known_properties:
                if property_name in self.known_properties[device_name]:
                    return ChangeType.DELETED
            return None

        # def* messages (new definition) indicate NEW or UPDATED
        if is_def_message:
            if device_name not in self.known_properties:
                return ChangeType.NEW
            if property_name not in self.known_properties[device_name]:
                return ChangeType.NEW
            return ChangeType.UPDATED

        # set* messages indicate UPDATED (property must exist)
        if device_name in self.known_properties:
            if property_name in self.known_properties[device_name]:
                return ChangeType.UPDATED

        # Unknown property receiving set* message (shouldn't happen, but handle gracefully)
        return None

    def add_device(self, device_name: str) -> None:
        """Register a known device."""
        self.known_devices.add(device_name)
        if device_name not in self.known_properties:
            self.known_properties[device_name] = set()

    def add_property(self, device_name: str, property_name: str) -> None:
        """Register a known property."""
        if device_name not in self.known_devices:
            self.add_device(device_name)
        self.known_properties[device_name].add(property_name)

    def remove_property(self, device_name: str, property_name: str) -> None:
        """Unregister a property."""
        if device_name in self.known_properties:
            self.known_properties[device_name].discard(property_name)

    def remove_device(self, device_name: str) -> None:
        """Unregister a device and all its properties."""
        self.known_devices.discard(device_name)
        if device_name in self.known_properties:
            del self.known_properties[device_name]

    def is_device_known(self, device_name: str) -> bool:
        """Check if device is known."""
        return device_name in self.known_devices

    def is_property_known(self, device_name: str, property_name: str) -> bool:
        """Check if property is known."""
        return (device_name in self.known_properties and
                property_name in self.known_properties[device_name])

    def get_known_devices(self) -> List[str]:
        """Get list of all known device names."""
        return list(self.known_devices)

    def get_known_properties(self, device_name: str) -> List[str]:
        """Get list of all known property names for a device."""
        return list(self.known_properties.get(device_name, set()))

    def clear(self) -> None:
        """Clear all known devices and properties."""
        self.known_devices.clear()
        self.known_properties.clear()
