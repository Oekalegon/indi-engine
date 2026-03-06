# INDI Engine protocol

This is the communication protocol between the INDI engine and clients of the engine (not betweem the engine and the INDI server).

## INDI messages forwarding.
All INDI messages that are comming from the server should still be forwarded. And any commands from the client towards the INDI server and drivers should also be forwarded. The format, however, will be different. We propose to use a JSON format instead of the XML format used in INDI server.

So, for instance, a

```xml
<defNumberVector device="CCD Simulator" name="CCD_EXPOSURE" label="Expose" group="Main Control" state="Idle" perm="rw" timeout="60" timestamp="2026-03-05T12:00:00">
  <defNumber name="CCD_EXPOSURE_VALUE" label="Duration (s)" format="%5.2f" min="0.001" max="3600" step="1">
    1.0
  </defNumber>
</defNumberVector>
```

will be forwarded as:

```json
{
    "device": "CCD Simulator",
    "property": "CCD_EXPOSURE",
    "data_type": "number",
    "label": "Expose",
    "group": "Main Control",
    "state": "Idle",
    "perm": "rw",
    "timeout": 60,
    "timestamp": "2026-03-05T12:00:00",
    "elements": [
        {
            "name": "CCD_EXPOSURE_VALUE",
            "label": "Duration (s)",
            "format": "%5.2f",
            "min": 0.001,
            "max": 3600.0,
            "step": 1.0,
            "value": 1.0
        }
    ]
}
```

### set — server reporting current state

A `set*Vector` message comes from the INDI server and represents the **current actual state** of a property. The engine forwards it to engine clients. Metadata fields (label, group, format, min, max, step) are omitted since they were already sent with the `def` message.

Each element also carries a `target_value` field: the last value the engine commanded via a `new` message, or `null` if no command has been sent yet. This allows clients to see both where a device currently is and where it was told to go.

Example: a mount midway through a slew to RA=10.5, DEC=45.0. The property state is `Busy` and the values reflect the current (moving) position:

```xml
<setNumberVector device="Telescope Simulator" name="EQUATORIAL_EOD_COORD" state="Busy" timestamp="2026-03-05T12:01:00">
  <oneNumber name="RA">10.1</oneNumber>
  <oneNumber name="DEC">42.3</oneNumber>
</setNumberVector>
```

forwarded as:

```json
{
    "device": "Telescope Simulator",
    "property": "EQUATORIAL_EOD_COORD",
    "data_type": "number",
    "state": "Busy",
    "timestamp": "2026-03-05T12:01:00",
    "elements": [
        {
            "name": "RA",
            "value": 10.1,
            "target_value": 10.5
        },
        {
            "name": "DEC",
            "value": 42.3,
            "target_value": 45.0
        }
    ]
}
```

### new — client commanding a new value

A `new` message originates from an engine client and represents a **command**: the value the client wants the device to move to. The engine translates it and forwards it to the INDI server as a `new*Vector` XML message.

Example: commanding the mount to slew to RA=10.5, DEC=45.0:

```json
{
    "type": "new",
    "device": "Telescope Simulator",
    "property": "EQUATORIAL_EOD_COORD",
    "data_type": "number",
    "elements": [
        {
            "name": "RA",
            "value": 10.5
        },
        {
            "name": "DEC",
            "value": 45.0
        }
    ]
}
```

forwarded to the INDI server as:

```xml
<newNumberVector device="Telescope Simulator" name="EQUATORIAL_EOD_COORD">
  <oneNumber name="RA">10.5</oneNumber>
  <oneNumber name="DEC">45.0</oneNumber>
</newNumberVector>
```

## Log messages

Log messages from the INDI server such as:

```xml
<message device="Telescope Simulator" message="Slew complete." timestamp="2026-03-05T12:01:30"/>
```

are forwarded to engine clients as:

```json
{
    "type": "message",
    "device": "Telescope Simulator",
    "message": "Slew complete.",
    "timestamp": "2026-03-05T12:01:30"
}
```

Server-level messages without a device use `null` for the `device` field:

```xml
<message message="INDI server started." timestamp="2026-03-05T12:00:00"/>
```

```json
{
    "type": "message",
    "device": null,
    "message": "INDI server started.",
    "timestamp": "2026-03-05T12:00:00"
}
```

## Message types summary

| type | direction | description |
|------|-----------|-------------|
| `def` | engine → client | Property definition with full metadata (sent once per property, and replayed to newly connected clients) |
| `set` | engine → client | Property value update from the INDI server |
| `new` | client → engine | Command a new property value; engine forwards to INDI server |
| `message` | engine → client | Log message from INDI server or engine component |
| `server_control` | client → engine | Start, stop, or restart indiserver |
| `server_status` | engine → client | Current indiserver state broadcast after any `server_control` command |

---

## Server control

### server_control — client commanding the server

A `server_control` message is sent from an engine client to start, stop, or restart the INDI server, or to query its current status.

| field | type | description |
|-------|------|-------------|
| `type` | string | `"server_control"` |
| `action` | string | `"status"`, `"start"`, `"stop"`, or `"restart"` |
| `drivers` | array of strings | (optional) override the driver list for `start` and `restart` |

Examples:

```json
{ "type": "server_control", "action": "status" }
```

```json
{ "type": "server_control", "action": "start" }
```

```json
{
    "type": "server_control",
    "action": "restart",
    "drivers": ["indi_simulator_telescope", "indi_simulator_ccd"]
}
```

```json
{ "type": "server_control", "action": "stop" }
```

### server_status — engine broadcasting server state

After every `server_control` command the engine broadcasts the current server state to **all** connected clients.

| field | type | description |
|-------|------|-------------|
| `type` | string | `"server_status"` |
| `running` | boolean | Whether indiserver is currently running |
| `indi_connected` | boolean | Whether the engine's INDI client is connected |
| `drivers` | array of strings | Currently loaded driver names |

Example:

```json
{
    "type": "server_status",
    "running": true,
    "indi_connected": true,
    "drivers": ["indi_simulator_telescope", "indi_simulator_ccd"]
}
```

---

## Log messages

Of course, the INDI engine will also produce log messages, such as imaging sequence started:

```json
{
    "type": "message",
    "device": null,
    "source": "imaging-sequencer",
    "message": "Imaging sequence finished",
    "timestamp": "2026-03-05T12:00:00",
    "context": {
        "id": "some UUID",
        "name": "M42 imaging",
        "status": "finished"
    }
}
```
