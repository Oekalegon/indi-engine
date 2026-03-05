"""INDI property, device, and element object models.

These classes mimic the PyIndi interface to maintain backward compatibility.
They are lightweight data holders with no dependency on libindi.
"""

from datetime import datetime
from typing import Dict, List, Optional, Union
from dataclasses import dataclass, field
from .constants import IndiPropertyType, IndiPropertyState, IndiPropertyPerm, IndiSwitchRule


@dataclass
class IPropertyElement:
    """Represents a single INDI property element (OneNumber, OneText, OneSwitch, OneLight).

    Attributes:
        name: Element name (e.g., "RA", "DEC", "TRACK")
        value: Element value (string representation)
        state: Element state
        type: Element property type
        label: Human-readable label (optional)
        format: Printf-style format string (e.g. "%8.4f") — number elements only
        min: Minimum allowed value — number elements only
        max: Maximum allowed value — number elements only
        step: Step size — number elements only
        blob_format: File format (e.g. ".fits") — blob elements only
        blob_size: Unencoded byte count — blob elements only
    """
    name: str
    value: Union[str, bytes] = ""
    state: IndiPropertyState = IndiPropertyState.IDLE
    type: IndiPropertyType = IndiPropertyType.UNKNOWN
    label: str = ""
    format: str = ""
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    blob_format: str = ""  # e.g. ".fits", ".cr2" — only meaningful for blob elements
    blob_size: int = 0     # unencoded byte count — only meaningful for blob elements

    def getName(self) -> str:
        """Get element name."""
        return self.name

    def getLabel(self) -> str:
        """Get element label."""
        return self.label

    def getValue(self) -> str:
        """Get element value as string."""
        return self.value

    def getText(self) -> str:
        """Get element text value (alias for value)."""
        return self.value

    def getState(self) -> IndiPropertyState:
        """Get element state."""
        return self.state

    def getFormat(self) -> str:
        """Get printf-style format string (number elements)."""
        return self.format

    def getMin(self) -> Optional[float]:
        """Get minimum allowed value (number elements)."""
        return self.min

    def getMax(self) -> Optional[float]:
        """Get maximum allowed value (number elements)."""
        return self.max

    def getStep(self) -> Optional[float]:
        """Get step size (number elements)."""
        return self.step

    def setValue(self, value: str) -> None:
        """Set element value."""
        self.value = value

    def setText(self, text: str) -> None:
        """Set element text value (alias for setValue)."""
        self.value = text

    def setState(self, state: IndiPropertyState) -> None:
        """Set element state."""
        self.state = state

    def getblobdata(self) -> bytes:
        """Get BLOB element data as bytes (PyIndi: getblobdata())."""
        if isinstance(self.value, bytes):
            return self.value
        return b""

    def getbloblen(self) -> int:
        """Get BLOB data length in bytes (PyIndi: getbloblen())."""
        return self.blob_size if self.blob_size > 0 else len(self.getblobdata())

    def getblobformat(self) -> str:
        """Get BLOB format string, e.g. '.fits' (PyIndi: getblobformat())."""
        return self.blob_format


@dataclass
class IProperty:
    """Represents an INDI property (Number, Text, Switch, Light, BLOB).

    A property contains multiple elements and belongs to a device.

    Attributes:
        device_name: Name of the device this property belongs to
        name: Property name (e.g., "EQUATORIAL_EOD_COORD", "CONNECTION")
        type: Property type
        state: Property state
        perm: Property permissions
        timestamp: Optional timestamp from server
        label: Human-readable label (optional)
        group: GUI group name (optional)
        rule: Switch rule (only meaningful for SWITCH type)
        elements: Dictionary of element name -> IPropertyElement
    """
    device_name: str
    name: str
    type: IndiPropertyType = IndiPropertyType.UNKNOWN
    state: IndiPropertyState = IndiPropertyState.IDLE
    perm: IndiPropertyPerm = IndiPropertyPerm.RW
    timestamp: Optional[datetime] = None
    label: str = ""
    group: str = ""
    rule: IndiSwitchRule = IndiSwitchRule.UNKNOWN
    elements: Dict[str, IPropertyElement] = field(default_factory=dict)

    def getDeviceName(self) -> str:
        """Get device name."""
        return self.device_name

    def getName(self) -> str:
        """Get property name."""
        return self.name

    def getType(self) -> IndiPropertyType:
        """Get property type."""
        return self.type

    def getState(self) -> IndiPropertyState:
        """Get property state."""
        return self.state

    def getPermission(self) -> IndiPropertyPerm:
        """Get property permission."""
        return self.perm

    def getTimestamp(self) -> Optional[datetime]:
        """Get property timestamp from server."""
        return self.timestamp

    def getLabel(self) -> str:
        """Get property label."""
        return self.label

    def getGroupName(self) -> str:
        """Get property group name."""
        return self.group

    def getRule(self) -> IndiSwitchRule:
        """Get switch rule (switch properties only)."""
        return self.rule

    def getRuleAsString(self) -> str:
        """Get switch rule as string (e.g. 'OneOfMany')."""
        return self.rule.value

    def getNumber(self) -> Optional[List[IPropertyElement]]:
        """Get number elements (for number properties)."""
        if self.type == IndiPropertyType.NUMBER:
            return list(self.elements.values())
        return None

    def getText(self) -> Optional[List[IPropertyElement]]:
        """Get text elements (for text properties)."""
        if self.type == IndiPropertyType.TEXT:
            return list(self.elements.values())
        return None

    def getSwitch(self) -> Optional[List[IPropertyElement]]:
        """Get switch elements (for switch properties)."""
        if self.type == IndiPropertyType.SWITCH:
            return list(self.elements.values())
        return None

    def getLight(self) -> Optional[List[IPropertyElement]]:
        """Get light elements (for light properties)."""
        if self.type == IndiPropertyType.LIGHT:
            return list(self.elements.values())
        return None

    def getBLOB(self) -> Optional[List[IPropertyElement]]:
        """Get BLOB elements (for BLOB properties)."""
        if self.type == IndiPropertyType.BLOB:
            return list(self.elements.values())
        return None

    def getElementCount(self) -> int:
        """Get number of elements in this property."""
        return len(self.elements)

    def getElement(self, name: str) -> Optional[IPropertyElement]:
        """Get a specific element by name."""
        return self.elements.get(name)

    def getElements(self) -> List[IPropertyElement]:
        """Get all elements."""
        return list(self.elements.values())

    def findOnSwitch(self) -> Optional[IPropertyElement]:
        """Return the first switch element with value 'On', or None."""
        for elem in self.elements.values():
            if elem.value == "On":
                return elem
        return None

    def findOnSwitchIndex(self) -> int:
        """Return index of first ON switch element, or -1 if none."""
        for i, elem in enumerate(self.elements.values()):
            if elem.value == "On":
                return i
        return -1

    def findOnSwitchName(self) -> str:
        """Return name of first ON switch element, or empty string."""
        elem = self.findOnSwitch()
        return elem.name if elem else ""

    def isSwitchOn(self, name: str) -> bool:
        """Return True if named switch element is On."""
        elem = self.elements.get(name)
        return elem is not None and elem.value == "On"

    def isNameMatch(self, name: str) -> bool:
        """Return True if this property's name matches the given name."""
        return self.name == name

    def isValid(self) -> bool:
        """Return True if this property has a device name, a name, and a known type."""
        return bool(self.device_name) and bool(self.name) and self.type != IndiPropertyType.UNKNOWN

    def __getitem__(self, index: int) -> IPropertyElement:
        """Get element by index."""
        return list(self.elements.values())[index]

    def __len__(self) -> int:
        """Return number of elements."""
        return len(self.elements)


@dataclass
class IDevice:
    """Represents an INDI device.

    A device contains multiple properties and may receive messages.

    Attributes:
        name: Device name (e.g., "Telescope Simulator", "CCD Camera")
        properties: Dictionary of property name -> IProperty
        messages: List of message strings from device
    """
    name: str
    properties: Dict[str, IProperty] = field(default_factory=dict)
    messages: List[str] = field(default_factory=list)

    def getDeviceName(self) -> str:
        """Get device name."""
        return self.name

    def getProperties(self) -> List[IProperty]:
        """Get all properties for this device."""
        return list(self.properties.values())

    def getProperty(self, name: str) -> Optional[IProperty]:
        """Get a specific property by name."""
        return self.properties.get(name)

    def getPropertyCount(self) -> int:
        """Get number of properties."""
        return len(self.properties)

    def isConnected(self) -> bool:
        """Return True if device's CONNECTION/CONNECT switch is On."""
        conn_prop = self.properties.get("CONNECTION")
        if conn_prop is None:
            return False
        connect_elem = conn_prop.elements.get("CONNECT")
        return connect_elem is not None and connect_elem.value == "On"

    def isNameMatch(self, name: str) -> bool:
        """Return True if this device's name matches the given name."""
        return self.name == name

    def getNumber(self, name: str) -> Optional["IProperty"]:
        """Get a number property by name, or None if not found or wrong type."""
        prop = self.properties.get(name)
        return prop if prop is not None and prop.type == IndiPropertyType.NUMBER else None

    def getText(self, name: str) -> Optional["IProperty"]:
        """Get a text property by name, or None if not found or wrong type."""
        prop = self.properties.get(name)
        return prop if prop is not None and prop.type == IndiPropertyType.TEXT else None

    def getSwitch(self, name: str) -> Optional["IProperty"]:
        """Get a switch property by name, or None if not found or wrong type."""
        prop = self.properties.get(name)
        return prop if prop is not None and prop.type == IndiPropertyType.SWITCH else None

    def getLight(self, name: str) -> Optional["IProperty"]:
        """Get a light property by name, or None if not found or wrong type."""
        prop = self.properties.get(name)
        return prop if prop is not None and prop.type == IndiPropertyType.LIGHT else None

    def getBLOB(self, name: str) -> Optional["IProperty"]:
        """Get a BLOB property by name, or None if not found or wrong type."""
        prop = self.properties.get(name)
        return prop if prop is not None and prop.type == IndiPropertyType.BLOB else None

    def messageQueue(self) -> List[str]:
        """Get message queue for this device."""
        return self.messages.copy()

    def addMessage(self, message: str) -> None:
        """Add a message to the device queue."""
        self.messages.append(message)

    def clearMessages(self) -> None:
        """Clear all messages from the queue."""
        self.messages.clear()


# ---------------------------------------------------------------------------
# Typed property wrappers (PyIndi compatibility)
# In PyIndi, these are C++ typed casts. Here they are thin wrappers that
# delegate all operations to the underlying IProperty.
# Usage: np = PropertyNumber(generic_prop)  →  iterate elements, call getters
# ---------------------------------------------------------------------------

class _TypedPropertyWrapper:
    """Base class for typed property wrappers."""

    def __init__(self, prop: IProperty):
        self._prop = prop

    def __getattr__(self, name):
        return getattr(self._prop, name)

    def __getitem__(self, index):
        return self._prop[index]

    def __len__(self):
        return len(self._prop)

    def __iter__(self):
        return iter(self._prop.elements.values())


class PropertyNumber(_TypedPropertyWrapper):
    """Typed wrapper for number vector properties (PyIndi: PropertyNumber)."""


class PropertyText(_TypedPropertyWrapper):
    """Typed wrapper for text vector properties (PyIndi: PropertyText)."""


class PropertySwitch(_TypedPropertyWrapper):
    """Typed wrapper for switch vector properties (PyIndi: PropertySwitch)."""


class PropertyLight(_TypedPropertyWrapper):
    """Typed wrapper for light vector properties (PyIndi: PropertyLight)."""


class PropertyBlob(_TypedPropertyWrapper):
    """Typed wrapper for BLOB vector properties (PyIndi: PropertyBlob)."""


# Legacy aliases matching older PyIndi naming
INumberVectorProperty = PropertyNumber
ITextVectorProperty   = PropertyText
ISwitchVectorProperty = PropertySwitch
ILightVectorProperty  = PropertyLight
IBLOBVectorProperty   = PropertyBlob
