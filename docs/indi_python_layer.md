# INDI Python Layer

Pure Python implementation of the INDI client protocol. No native dependencies — no `libindi`, no `pyindi-client`, no SWIG. Runs anywhere Python runs, including the Raspberry Pi.

## Overview

The layer sits between the INDI server (running on the same machine) and the rest of INDIEngine. It handles the full INDI XML protocol: connecting, receiving property definitions and updates, sending commands, and delivering FITS image data.

```
      INDI Server (port 7624)
                │  XML over TCP
                ▼
 ┌──────────────────────────────┐
 │  indi_engine.indi.protocol   │
 │  ┌──────────┐  ┌──────────┐  │
 │  │ transport│  │  parser  │  │
 │  └────┬─────┘  └─────┬────┘  │
 │       └──────┬───────┘       │
 │         ┌────▼────┐          │
 │         │ client  │          │
 │         └────┬────┘          │
 └──────────────┼───────────────┘
                │ callbacks / IDevice / IProperty
                ▼
         INDIEngine logic
```

**Layers:**
- `transport` — TCP socket with framing; delivers complete XML messages
- `parser` — converts raw XML bytes into typed `IndiMessage` objects
- `state` — tracks which devices/properties are known; detects new vs updated
- `client` — orchestrates everything; fires callbacks; exposes the send API
- `properties` — `IDevice`, `IProperty`, `IPropertyElement` data model

---

## Quick Start

```python
from indi_engine.indi.client import IndiClient

client = IndiClient(host="localhost", port=7624)
client.connectServer()
client.watchDevice()  # subscribe to all devices
```

`IndiClient` is the recommended entry point. It extends `PurePythonIndiClient` with logging callbacks already wired up.

---

## Callbacks

Override or replace callbacks to react to events. All callbacks are invoked from the reader thread — keep them short; defer heavy work.

```python
from indi_engine.indi.client import IndiClient

class MyClient(IndiClient):

    def setup_callbacks(self):
        super().setup_callbacks()
        self.newDevice    = self.on_new_device
        self.newProperty  = self.on_new_property
        self.updateProperty = self.on_update
        self.newBLOB      = self.on_blob
        self.newMessage   = self.on_message
        self.newUniversalMessage = self.on_server_message

    def on_new_device(self, device):
        print(f"Device appeared: {device.getDeviceName()}")

    def on_new_property(self, prop):
        print(f"  {prop.getDeviceName()}/{prop.getName()} ({prop.getType().value})")

    def on_update(self, prop):
        print(f"  Updated: {prop.getDeviceName()}/{prop.getName()}")

    def on_blob(self, prop):
        # Called when a camera delivers a frame
        for elem in prop:
            fits_bytes = elem.getblobdata()
            print(f"  FITS frame: {len(fits_bytes)} bytes, format={elem.getblobformat()}")

    def on_message(self, device, text):
        print(f"  [{device.getDeviceName()}] {text}")

    def on_server_message(self, text):
        # Messages not tied to any device (e.g. "INDI server ready")
        print(f"  [server] {text}")
```

### Full callback list

| Callback | Signature | When fired |
|---|---|---|
| `serverConnected` | `()` | TCP connection established |
| `serverDisconnected` | `(code)` | Connection lost (0=clean, 1=error) |
| `newDevice` | `(device: IDevice)` | First property seen for a new device |
| `removeDevice` | `(device: IDevice)` | `delDevice` received |
| `newProperty` | `(prop: IProperty)` | `def*Vector` for a previously unseen property |
| `updateProperty` | `(prop: IProperty)` | `set*Vector` or re-sent `def*Vector` |
| `removeProperty` | `(prop: IProperty)` | `delProperty` received |
| `newBLOB` | `(prop: IProperty)` | `setBLOBVector` received (camera frame) |
| `newMessage` | `(device: IDevice, text: str)` | `<message device="...">` |
| `newUniversalMessage` | `(text: str)` | `<message>` with no device attribute |

---

## Reading Device State

After `watchDevice()` is called the client populates an in-memory model as properties arrive.

### Get all known devices

```python
devices = client.getDevices()   # list[IDevice]
for device in devices:
    print(device.getDeviceName())
```

### Get a specific device

```python
telescope = client.getDevice("Telescope Simulator")
if telescope is None:
    print("Not yet seen")
```

### Check if a device is connected

```python
if telescope.isConnected():
    print("Telescope is connected to INDI")
```

### Get all properties of a device

```python
for prop in telescope.getProperties():
    print(f"  {prop.getName()}: {prop.getType().value} [{prop.getState().value}]")
```

### Get a property by name

```python
# Generic lookup
prop = telescope.getProperty("EQUATORIAL_EOD_COORD")

# Typed lookups (return None if wrong type or not found)
radec  = telescope.getNumber("EQUATORIAL_EOD_COORD")
mode   = telescope.getSwitch("TRACK_MODE")
status = telescope.getLight("TELESCOPE_STATUS")
header = telescope.getText("FITS_HEADER")
image  = telescope.getBLOB("CCD1")
```

### Read element values from a number property

```python
radec = telescope.getNumber("EQUATORIAL_EOD_COORD")
if radec:
    for elem in radec:
        print(f"  {elem.getName()} = {elem.getValue()}")
        # For number elements: min, max, step, format are also available
        print(f"    range: {elem.getMin()} – {elem.getMax()}, step={elem.getStep()}")

# Or by index
ra  = radec[0]
dec = radec[1]

# Or by element name
ra_elem = radec.getElement("RA")
print(ra_elem.getValue())
```

### Read a switch property

```python
track = telescope.getSwitch("TRACK_MODE")
if track:
    # Find which mode is active
    active = track.findOnSwitch()          # IPropertyElement or None
    name   = track.findOnSwitchName()      # "TRACK_SIDEREAL" etc.
    index  = track.findOnSwitchIndex()     # 0-based

    # Check a specific switch
    if track.isSwitchOn("TRACK_SIDEREAL"):
        print("Sidereal tracking active")
```

### Property metadata

```python
prop = telescope.getNumber("EQUATORIAL_EOD_COORD")
print(prop.getName())           # "EQUATORIAL_EOD_COORD"
print(prop.getLabel())          # "Equatorial JNow"
print(prop.getGroupName())      # "Main Control"
print(prop.getState().value)    # "Ok", "Busy", "Idle", "Alert"
print(prop.getPermission())     # IndiPropertyPerm.RO / RW / WO
print(prop.getTimestamp())      # datetime (UTC) or None
print(prop.isValid())           # True if device+name+type all set
print(prop.isNameMatch("EQUATORIAL_EOD_COORD"))  # True
```

---

## Sending Commands

### Connect / disconnect a device

```python
client.connectDevice("Telescope Simulator")
client.disconnectDevice("Telescope Simulator")
```

### Send a number (single element convenience form)

```python
client.sendNewNumber("Telescope Simulator", "EQUATORIAL_EOD_COORD", "RA", 5.667)
client.sendNewNumber("Telescope Simulator", "EQUATORIAL_EOD_COORD", "DEC", -5.0)
```

### Send a number (full property form)

```python
prop = telescope.getNumber("EQUATORIAL_EOD_COORD")
prop.getElement("RA").setValue("5.667")
prop.getElement("DEC").setValue("-5.0")
client.sendNewNumber(prop)
```

### Send a switch

```python
# Convenience: set a named switch to On
client.sendNewSwitch("Telescope Simulator", "TRACK_MODE", "TRACK_SIDEREAL")

# Full property form (send all element values as-is)
mode = telescope.getSwitch("TRACK_MODE")
client.sendNewSwitch(mode)
```

### Send text

```python
client.sendNewText("CCD Simulator", "FITS_HEADER", "OBSERVER", "Don Willems")
```

### Subscribe to a specific property only

```python
# Watch all devices
client.watchDevice()

# Watch one device
client.watchDevice("CCD Simulator")

# Watch one specific property
client.watchProperty("CCD Simulator", "CCD_EXPOSURE")
```

### Request a camera exposure

```python
client.setBLOBMode("Also", device="CCD Simulator")  # enable BLOB reception
client.sendNewNumber("CCD Simulator", "CCD_EXPOSURE", "CCD_EXPOSURE_VALUE", 10.0)
# → triggers newBLOB callback when the frame arrives
```

---

## Receiving FITS Frames

```python
import pathlib

def on_blob(prop):
    for elem in prop:
        fits = elem.getblobdata()     # raw bytes
        fmt  = elem.getblobformat()   # ".fits", ".cr2", etc.
        size = elem.getbloblen()      # unencoded byte count

        path = pathlib.Path(f"/tmp/{prop.getDeviceName()}_{prop.getName()}{fmt}")
        path.write_bytes(fits)
        print(f"Saved {len(fits)} bytes → {path}")

client.newBLOB = on_blob
client.setBLOBMode("Also", device="CCD Simulator")
```

---

## PyIndi Compatibility

The layer is a drop-in replacement for `pyindi-client`. Code written against PyIndi works without changes.

### C-style constants

```python
from indi_engine.indi.protocol.constants import (
    INDI_NUMBER, INDI_TEXT, INDI_SWITCH, INDI_LIGHT, INDI_BLOB,
    IPS_IDLE, IPS_OK, IPS_BUSY, IPS_ALERT,
    ISS_ON, ISS_OFF,
    IPV_RO, IPV_WO, IPV_RW,
    ISR_ONEOFMANY, ISR_ATMOST_ONE, ISR_NOFMANY,
    B_NEVER, B_ALSO, B_ONLY,
)

if prop.getType() == INDI_NUMBER:
    ...
if prop.getState() == IPS_BUSY:
    print("Telescope is slewing")
```

### Typed property wrappers

```python
from indi_engine.indi.protocol.properties import PropertyNumber, PropertySwitch

# Cast a generic property to a typed wrapper (PyIndi pattern)
np = PropertyNumber(generic_prop)
for elem in np:
    print(elem.getName(), elem.getValue())

# Legacy class names also work
from indi_engine.indi.protocol.properties import INumberVectorProperty
np = INumberVectorProperty(generic_prop)
```

### BLOBHandling enum

```python
from indi_engine.indi.protocol.constants import BLOBHandling

client.setBLOBMode(BLOBHandling.B_ALSO, device="CCD Simulator")
client.setBLOBMode(BLOBHandling.B_NEVER, device="CCD Simulator")
```

---

## Error Handling

```python
from indi_engine.indi.protocol.errors import IndiConnectionError, IndiDisconnectedError

try:
    client.connectServer()
except IndiConnectionError as e:
    print(f"Could not connect: {e}")

try:
    client.sendNewNumber("Telescope", "RADEC", "RA", 5.0)
except IndiDisconnectedError:
    print("Lost connection before send")
```

---

## Module Reference

| Module | Contents |
|---|---|
| `indi_engine.indi.client` | `IndiClient` — recommended entry point with logging |
| `indi_engine.indi.protocol.client` | `PurePythonIndiClient` — base class, all protocol logic |
| `indi_engine.indi.protocol.properties` | `IDevice`, `IProperty`, `IPropertyElement`, typed wrappers |
| `indi_engine.indi.protocol.constants` | Enums and PyIndi-compatible constants |
| `indi_engine.indi.protocol.parser` | `IndiXmlParser`, `IndiMessage` |
| `indi_engine.indi.protocol.transport` | `IndiTransport` — TCP framing |
| `indi_engine.indi.protocol.errors` | `IndiConnectionError`, `IndiDisconnectedError`, `IndiProtocolError` |
