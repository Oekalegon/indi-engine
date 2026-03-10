"""INDI protocol constants and enums."""

from enum import Enum, auto


class IndiPropertyType(Enum):
    """INDI property types."""
    NUMBER = "number"
    TEXT = "text"
    SWITCH = "switch"
    LIGHT = "light"
    BLOB = "blob"
    UNKNOWN = "unknown"


class IndiPropertyState(Enum):
    """INDI property state."""
    IDLE = "Idle"
    OK = "Ok"
    BUSY = "Busy"
    ALERT = "Alert"
    UNKNOWN = "Unknown"


class IndiPropertyPerm(Enum):
    """INDI property permissions."""
    RO = "ro"  # Read-only
    WO = "wo"  # Write-only
    RW = "rw"  # Read-write


class IndiSwitchRule(Enum):
    """INDI switch vector rule (how many switches can be ON simultaneously)."""
    ONE_OF_MANY = "OneOfMany"
    AT_MOST_ONE = "AtMostOne"
    ANY_OF_MANY = "AnyOfMany"
    UNKNOWN = "Unknown"


class IndiSwitchType(Enum):
    """INDI switch element types."""
    SWITCH_ONEOFMANY = "OneOfMany"
    SWITCH_ATMOST_ONE = "AtMostOne"
    SWITCH_ANY = "AnyOfMany"
    SWITCH_UNKNOWN = "Unknown"


class IndiSwitchStatus(Enum):
    """INDI switch element status."""
    ON = "On"
    OFF = "Off"
    UNKNOWN = "Unknown"


class IndiLightStatus(Enum):
    """INDI light element status."""
    IDLE = "Idle"
    OK = "Ok"
    BUSY = "Busy"
    ALERT = "Alert"
    UNKNOWN = "Unknown"


class BLOBHandling(Enum):
    """INDI BLOB handling mode."""
    B_NEVER = "Never"  # Never receive BLOBs
    B_ALSO = "Also"    # Receive BLOBs alongside other updates
    B_ONLY = "Only"    # Receive only BLOBs


class IndiMessageType(Enum):
    """INDI XML message types."""
    def_number = auto()
    def_text = auto()
    def_switch = auto()
    def_light = auto()
    def_blob = auto()
    set_number = auto()
    set_text = auto()
    set_switch = auto()
    set_light = auto()
    set_blob = auto()
    message = auto()
    del_property = auto()
    del_device = auto()
    new_blob = auto()
    unknown = auto()


# Map XML element names to message types
MESSAGE_TYPE_MAP = {
    "defNumberVector": IndiMessageType.def_number,
    "defTextVector": IndiMessageType.def_text,
    "defSwitchVector": IndiMessageType.def_switch,
    "defLightVector": IndiMessageType.def_light,
    "defBLOBVector": IndiMessageType.def_blob,
    "setNumberVector": IndiMessageType.set_number,
    "setTextVector": IndiMessageType.set_text,
    "setSwitchVector": IndiMessageType.set_switch,
    "setLightVector": IndiMessageType.set_light,
    "setBLOBVector": IndiMessageType.set_blob,
    "message": IndiMessageType.message,
    "delProperty": IndiMessageType.del_property,
    "delDevice": IndiMessageType.del_device,
    "newBLOBVector": IndiMessageType.new_blob,
}

# ---------------------------------------------------------------------------
# PyIndi-compatible C-style constants (aliases to enum values)
# These allow code written against PyIndi to work without modification.
# ---------------------------------------------------------------------------

# Property types (INDI_NUMBER, INDI_TEXT, etc.)
INDI_NUMBER = IndiPropertyType.NUMBER
INDI_TEXT   = IndiPropertyType.TEXT
INDI_SWITCH = IndiPropertyType.SWITCH
INDI_LIGHT  = IndiPropertyType.LIGHT
INDI_BLOB   = IndiPropertyType.BLOB

# Property states (IPS_IDLE, IPS_OK, IPS_BUSY, IPS_ALERT)
IPS_IDLE  = IndiPropertyState.IDLE
IPS_OK    = IndiPropertyState.OK
IPS_BUSY  = IndiPropertyState.BUSY
IPS_ALERT = IndiPropertyState.ALERT

# Switch states (ISS_OFF, ISS_ON)
ISS_OFF = "Off"
ISS_ON  = "On"

# Property permissions (IPV_RO, IPV_WO, IPV_RW)
IPV_RO = IndiPropertyPerm.RO
IPV_WO = IndiPropertyPerm.WO
IPV_RW = IndiPropertyPerm.RW

# Switch rules (ISR_ONEOFMANY, ISR_ATMOST_ONE, ISR_NOFMANY)
ISR_ONEOFMANY = IndiSwitchRule.ONE_OF_MANY
ISR_ATMOST_ONE = IndiSwitchRule.AT_MOST_ONE
ISR_NOFMANY   = IndiSwitchRule.ANY_OF_MANY

# BLOB handling (B_NEVER, B_ALSO, B_ONLY)
B_NEVER = BLOBHandling.B_NEVER
B_ALSO  = BLOBHandling.B_ALSO
B_ONLY  = BLOBHandling.B_ONLY

# Default INDI server connection parameters
INDI_HOST_DEFAULT = "localhost"
INDI_PORT_DEFAULT = 7624

# Socket timeout and reconnection parameters
SOCKET_TIMEOUT = 30  # seconds
RECV_BUFFER_SIZE = 262144  # 256 KB — large chunks reduce O(n²) cost for big BLOBs
RECONNECT_MIN_DELAY = 2  # seconds (initial backoff)
RECONNECT_MAX_DELAY = 60  # seconds (maximum backoff)
RECONNECT_BACKOFF_FACTOR = 2  # exponential backoff multiplier
