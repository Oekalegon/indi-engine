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
| `def` | engine → client | Property definition with full metadata (sent once per property, and replayed on subscribe) |
| `set` | engine → client | Property value update from the INDI server |
| `new` | client → engine | Command a new property value; engine forwards to INDI server |
| `message` | engine → client | Log message from INDI server or engine component |
| `subscribe` | client → engine | Subscribe to all messages or a specific device |
| `subscribe_ack` | engine → client | Subscription confirmed; state snapshot follows |
| `unsubscribe` | client → engine | Remove a subscription |
| `unsubscribe_ack` | engine → client | Unsubscription confirmed |
| `device_control` | client → engine | List known devices or get full property state for one device |
| `device_list` | engine → client | Response to `device_control` `list` action |
| `device_info` | engine → client | Response to `device_control` `get` action |
| `device_error` | engine → client | Error response to a failed `device_control` action |
| `capability_request` | client → engine | Request engine identity and capabilities |
| `capability_response` | engine → client | Engine identity, devices, scripts, and capabilities |
| `engine_list_request` | client → engine | Request list of known peer engines |
| `engine_list_response` | engine → client | List of known peer engines |
| `engine_online` | engine → client | Broadcast when a peer engine is discovered via mDNS |
| `engine_offline` | engine → client | Broadcast when a peer engine disappears from mDNS |
| `server_control` | client → engine | Start, stop, or restart indiserver |
| `server_status` | engine → client | Current indiserver state broadcast after any `server_control` command |
| `frame_control` | client → engine | List, retrieve, or delete captured image frames |
| `frame_ready` | engine → client | Broadcast when a new frame has been saved to disk |
| `frame_list` | engine → client | Response to `frame_control` `list` action |
| `frame_data` | engine → client | Response to `frame_control` `get` action — base64 image bytes |
| `frame_delete_ack` | engine → client | Response to `frame_control` `delete` action |
| `frame_error` | engine → client | Error response to any failed `frame_control` action |
| `script_control` | client → engine | List, describe, run, cancel, upload, delete, or list active runs of scripts |
| `script_status` | engine → client | Script lifecycle and progress updates broadcast to all clients |
| `script_list` | engine → client | Response to `script_control` `list` action |
| `script_info` | engine → client | Response to `script_control` `info` action — full script metadata |
| `script_runs` | engine → client | Response to `script_control` `list_runs` action |
| `script_cancel_ack` | engine → client | Response to `script_control` `cancel` action |
| `script_upload_ack` | engine → client | Response to `script_control` `upload` action |
| `script_delete_ack` | engine → client | Response to `script_control` `delete` action |
| `script_error` | engine → client | Error response to any failed `script_control` action |

---

## Provenance

Every message broadcast by an engine carries a `provenance` field — an ordered list of identifiers showing where the message originated and which engines forwarded it. Clients can use this to trace the full path of a message through the network.

The first entry is the INDI server that produced the data (`indi://host:port`). Each engine that forwards the message appends its own UUID.

```json
{
    "type": "set",
    "device": "Telescope Simulator",
    "property": "EQUATORIAL_EOD_COORD",
    "provenance": [
        "indi://localhost:7624",
        "550e8400-e29b-41d4-a716-446655440000",
        "6ba7b810-9dad-11d1-80b4-00c04fd430c8"
    ],
    "...": "..."
}
```

Engines use the provenance list for loop prevention: if an engine's own UUID is already present, the message is dropped instead of forwarded again.

---

## Subscriptions

Clients receive **no messages** until they subscribe. This applies to both regular clients and relay engines connecting to a peer.

### subscribe — client subscribing to messages

| field | type | description |
|-------|------|-------------|
| `type` | string | `"subscribe"` |
| `device` | string | (optional) subscribe to a specific device only; omit to subscribe to all |

```json
{ "type": "subscribe" }
```

```json
{ "type": "subscribe", "device": "Telescope Simulator" }
```

After a successful subscription the engine immediately sends a state snapshot: all current `def` messages for the subscribed devices. Subsequent updates arrive as `set` messages.

### subscribe_ack — engine confirming subscription

Sent only to the subscribing client.

```json
{ "type": "subscribe_ack", "device": null, "ok": true }
```

```json
{ "type": "subscribe_ack", "device": "Telescope Simulator", "ok": true }
```

### unsubscribe — client removing a subscription

```json
{ "type": "unsubscribe" }
```

```json
{ "type": "unsubscribe", "device": "Telescope Simulator" }
```

### unsubscribe_ack — engine confirming removal

```json
{ "type": "unsubscribe_ack", "device": null, "ok": true }
```

---

## Device control

### device_control — client querying device state

#### list — list all known devices

```json
{ "type": "device_control", "action": "list" }
```

Response (`device_list`) sent to the requester:

```json
{
    "type": "device_list",
    "devices": ["Telescope Simulator", "CCD Simulator"]
}
```

#### get — get full property state for a device

```json
{ "type": "device_control", "action": "get", "device": "Telescope Simulator" }
```

Response (`device_info`) sent to the requester. Properties are included without a `type` field (the INDI message type is not meaningful here):

```json
{
    "type": "device_info",
    "device": "Telescope Simulator",
    "connected": true,
    "properties": [
        {
            "property": "EQUATORIAL_EOD_COORD",
            "data_type": "number",
            "label": "Eq. Coordinates",
            "state": "Ok",
            "elements": [
                { "name": "RA",  "value": 5.0 },
                { "name": "DEC", "value": 20.0 }
            ]
        }
    ]
}
```

### device_error — error response

Sent to the requester when a `device_control` action fails (e.g. unknown device, missing field):

```json
{ "type": "device_error", "message": "Unknown device: Foo" }
```

---

## Capabilities

### capability_request — client requesting engine info

```json
{ "type": "capability_request" }
```

### capability_response — engine responding with its identity and capabilities

Sent only to the requesting client.

| field | type | description |
|-------|------|-------------|
| `type` | string | `"capability_response"` |
| `engine_id` | string | Stable UUID of this engine |
| `name` | string | Human-readable engine name |
| `devices` | array of strings | Names of currently known INDI devices |
| `capabilities` | array of objects | Declared capabilities (see below) |

Each capability object has:

| field | type | description |
|-------|------|-------------|
| `id` | string | Standardised capability identifier (see capability identifiers below) |
| `script` | string \| null | Script filename backing this capability, or `null` for non-script capabilities |

```json
{
    "type": "capability_response",
    "engine_id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "my-engine",
    "devices": ["Telescope Simulator", "CCD Simulator"],
    "capabilities": [
        {"id": "indi_proxy",                    "script": null},
        {"id": "slew_telescope_and_track",       "script": "slew_and_track.py"},
        {"id": "capture_dark_frames",            "script": "dark_frames.py"},
        {"id": "custom_scripts",                 "script": null}
    ]
}
```

### Capability identifiers

Well-known capability IDs:

| id | meaning |
|----|---------|
| `indi_proxy` | Engine forwards INDI device data from an indiserver |
| `slew_telescope_and_track` | Engine can slew a telescope to given coordinates and start tracking |
| `capture_frame` | Engine can capture a single light frame with a CCD camera |
| `capture_dark_frames` | Engine can capture a series of dark frames |
| `custom_scripts` | Engine accepts arbitrary user-uploaded scripts |

Engines may define additional capability IDs for custom workflows. IDs should use `snake_case`.

---

## Engine discovery

Engines advertise themselves via Bonjour/mDNS (`_indiengine._tcp.local.`). Connected clients receive events as peers appear and disappear, and can query the known engine list at any time.

### engine_online — peer engine appeared

Broadcast to all subscribed clients when a peer engine is discovered on the network.

| field | type | description |
|-------|------|-------------|
| `type` | string | `"engine_online"` |
| `engine_id` | string | UUID of the discovered engine |
| `name` | string | Human-readable name |
| `host` | string | IP address |
| `port` | integer | TCP port of the engine's socket server |
| `capabilities` | array of strings | Capabilities advertised by the peer |

```json
{
    "type": "engine_online",
    "engine_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
    "name": "engine-b",
    "host": "192.168.1.11",
    "port": 8625,
    "capabilities": ["indi_proxy"]
}
```

### engine_offline — peer engine disappeared

Broadcast to all subscribed clients when a peer engine stops advertising on mDNS.

```json
{
    "type": "engine_offline",
    "engine_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
    "name": "engine-b"
}
```

### engine_list_request — client requesting known peers

```json
{ "type": "engine_list_request" }
```

### engine_list_response — engine responding with known peers

Sent only to the requesting client.

```json
{
    "type": "engine_list_response",
    "engines": [
        {
            "engine_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
            "name": "engine-b",
            "host": "192.168.1.11",
            "port": 8625,
            "capabilities": ["indi_proxy"]
        }
    ]
}
```

---

## Frames

When a CCD camera completes an exposure, the engine receives the image data from the INDI server as a BLOB and stores it locally on disk (`data/frames/` by default). A `frame_ready` event is then broadcast to all subscribed clients. Clients can later retrieve the binary data and, once they have verified it, ask the engine to delete it.

Scripts must call `indi.enable_blobs(device)` before triggering an exposure so the INDI server knows to send image data to the engine.

### frame_ready — new frame saved

Broadcast to all subscribed clients immediately after the engine saves an incoming image.

| field | type | description |
|-------|------|-------------|
| `type` | string | `"frame_ready"` |
| `frame_id` | string | UUID identifying this frame |
| `device` | string | CCD device that produced the image |
| `run_id` | string \| null | Script run that triggered the capture, or `null` |
| `timestamp` | string | ISO 8601 UTC timestamp |
| `hash` | string | SHA-256 hex digest of the stored bytes |
| `size` | integer | File size in bytes |
| `format` | string | File extension, e.g. `".fits"` |
| `capture` | object | Capture settings used for this frame (see below) |

The `capture` object contains the settings that were active when the exposure was taken:

| field | type | description |
|-------|------|-------------|
| `exposure` | number | Exposure duration in seconds |
| `frame_type` | string | `"light"`, `"dark"`, `"flat"`, `"bias"`, or `"dark_flat"` |
| `frame_index` | integer | 1-based position of this frame within the sequence |
| `count` | integer | Total number of frames in the sequence |
| `gain` | number \| null | Sensor gain, or `null` if not set |
| `offset` | number \| null | Sensor offset (black level), or `null` if not set |
| `bin_x` | integer | Horizontal binning factor |
| `bin_y` | integer | Vertical binning factor |
| `frame_x` | integer \| null | Sub-frame X origin (pixels), or `null` for full sensor |
| `frame_y` | integer \| null | Sub-frame Y origin (pixels), or `null` for full sensor |
| `frame_w` | integer \| null | Sub-frame width (pixels), or `null` for full sensor |
| `frame_h` | integer \| null | Sub-frame height (pixels), or `null` for full sensor |
| `filter_name` | string \| null | Filter used, or `null` if no filter wheel |
| `cooler_temp` | number \| null | Target cooler temperature in °C, or `null` if cooler not used |
| `sensor_temp` | number \| null | Actual sensor temperature in °C at the moment of exposure, or `null` if unavailable |

```json
{
    "type": "frame_ready",
    "frame_id": "3f2504e0-4f89-11d3-9a0c-0305e82c3301",
    "device": "CCD Simulator",
    "run_id": "a1b2c3d4…",
    "timestamp": "2026-03-08T21:00:00+00:00",
    "hash": "e3b0c44298fc1c14…",
    "size": 2880,
    "format": ".fits",
    "capture": {
        "exposure": 30.0,
        "frame_type": "light",
        "frame_index": 4,
        "count": 10,
        "gain": 100,
        "offset": 10,
        "bin_x": 1,
        "bin_y": 1,
        "frame_x": null,
        "frame_y": null,
        "frame_w": null,
        "frame_h": null,
        "filter_name": "Ha",
        "cooler_temp": -10.0,
        "sensor_temp": -9.8
    }
}
```

### frame_control — client managing frames

#### list — list all stored frames

```json
{ "type": "frame_control", "action": "list" }
```

Response (`frame_list`) sent to the requester:

```json
{
    "type": "frame_list",
    "frames": [
        {
            "frame_id": "3f2504e0-…",
            "device": "CCD Simulator",
            "run_id": "a1b2c3d4…",
            "timestamp": "2026-03-08T21:00:00+00:00",
            "hash": "e3b0c442…",
            "size": 2880,
            "format": ".fits",
            "capture": {
                "exposure": 30.0,
                "frame_type": "light",
                "frame_index": 4,
                "count": 10,
                "gain": 100,
                "bin_x": 1,
                "bin_y": 1,
                "filter_name": "Ha",
                "cooler_temp": -10.0,
        "sensor_temp": -9.8
            }
        }
    ]
}
```

#### get — retrieve a frame

```json
{ "type": "frame_control", "action": "get", "frame_id": "3f2504e0-…" }
```

Response (`frame_data`) sent to the requester. The `data` field is the raw image bytes encoded as base64:

```json
{
    "type": "frame_data",
    "frame_id": "3f2504e0-…",
    "device": "CCD Simulator",
    "run_id": "a1b2c3d4…",
    "hash": "e3b0c442…",
    "format": ".fits",
    "size": 2880,
    "data": "<base64-encoded bytes>",
    "capture": {
        "exposure": 30.0,
        "frame_type": "light",
        "frame_index": 4,
        "count": 10,
        "gain": 100,
        "bin_x": 1,
        "bin_y": 1,
        "filter_name": "Ha",
        "cooler_temp": -10.0,
        "sensor_temp": -9.8
    }
}
```

The client should verify that `SHA-256(base64_decode(data)) == hash` before accepting the image.

#### delete — delete a frame after verification

The client must supply the hash it received with the frame data. The engine re-checks the hash against the stored value before deleting, so a frame cannot be accidentally removed before the client has confirmed a good download.

```json
{ "type": "frame_control", "action": "delete", "frame_id": "3f2504e0-…", "hash": "e3b0c442…" }
```

Response (`frame_delete_ack`):

```json
{ "type": "frame_delete_ack", "frame_id": "3f2504e0-…", "ok": true }
```

### frame_error — error response

```json
{ "type": "frame_error", "message": "Frame '3f2504e0-…' not found" }
```

Common causes: unknown `frame_id`, hash mismatch on delete, frame store not available.

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

---

## Script control

### script_control — client managing scripts

A `script_control` message is sent from an engine client to manage scripts.

| field | type | description |
|-------|------|-------------|
| `type` | string | `"script_control"` |
| `action` | string | One of `"list"`, `"run"`, `"cancel"`, `"upload"`, `"delete"`, `"list_runs"` |

#### list — list available scripts

```json
{ "type": "script_control", "action": "list" }
```

Response (`script_list`). Each entry includes the capability ID and parameter list from the companion metadata file:

```json
{
    "type": "script_list",
    "scripts": [
        {
            "name": "slew_and_track",
            "builtin": true,
            "capability_id": "slew_telescope_and_track",
            "description": "Slew the telescope to RA/DEC coordinates and start tracking.",
            "params": [
                {"name": "ra",  "description": "Right Ascension in hours", "type": "float", "required": true,  "min": 0.0, "max": 24.0},
                {"name": "dec", "description": "Declination in degrees",   "type": "float", "required": true,  "min": -90.0, "max": 90.0},
                {"name": "device", "description": "Telescope device name", "type": "string", "required": false, "default": "Telescope Simulator"}
            ]
        }
    ]
}
```

#### info — get full metadata for a single script

```json
{ "type": "script_control", "action": "info", "name": "slew_and_track" }
```

Response (`script_info`) sent to the requester:

```json
{
    "type": "script_info",
    "name": "slew_and_track",
    "builtin": true,
    "capability_id": "slew_telescope_and_track",
    "description": "Slew the telescope to RA/DEC coordinates and start tracking.",
    "params": [
        {"name": "ra",     "description": "Right Ascension in hours", "type": "float",  "required": true,  "min": 0.0,   "max": 24.0},
        {"name": "dec",    "description": "Declination in degrees",   "type": "float",  "required": true,  "min": -90.0, "max": 90.0},
        {"name": "device", "description": "Telescope device name",    "type": "string", "required": false, "default": "Telescope Simulator"}
    ]
}
```

Each parameter object has:

| field | type | description |
|-------|------|-------------|
| `name` | string | Parameter name (used as key in `params` when running) |
| `description` | string | Human-readable description |
| `type` | string | `"float"`, `"int"`, `"string"`, or `"bool"` |
| `required` | boolean | Whether the parameter must be supplied |
| `default` | any | Default value when `required` is false |
| `min` | number | (numeric types) Minimum allowed value |
| `max` | number | (numeric types) Maximum allowed value |
| `step` | number | (numeric types) Suggested step for UI sliders |

#### run — run a script

```json
{
    "type": "script_control",
    "action": "run",
    "name": "slew_and_track",
    "params": { "ra": 5.0, "dec": 20.0 }
}
```

The engine immediately starts broadcasting `script_status` messages to **all** clients (see below). There is no direct response to the requester.

#### cancel — cancel a running script

```json
{ "type": "script_control", "action": "cancel", "run_id": "<run_id>" }
```

Response (`script_cancel_ack`) sent to the requester:

```json
{ "type": "script_cancel_ack", "run_id": "<run_id>", "ok": true }
```

#### upload — upload a user script

```json
{
    "type": "script_control",
    "action": "upload",
    "name": "my_script",
    "content": "log('hello')"
}
```

Response (`script_upload_ack`) sent to the requester:

```json
{ "type": "script_upload_ack", "name": "my_script", "ok": true }
```

#### delete — delete a user script

```json
{ "type": "script_control", "action": "delete", "name": "my_script" }
```

Response (`script_delete_ack`) sent to the requester:

```json
{ "type": "script_delete_ack", "name": "my_script", "ok": true }
```

Attempting to delete a built-in script returns a `script_error`.

#### list_runs — list currently running scripts

```json
{ "type": "script_control", "action": "list_runs" }
```

Response (`script_runs`) sent to the requester:

```json
{
    "type": "script_runs",
    "runs": [
        { "run_id": "<run_id>", "name": "slew_and_track", "status": "running" }
    ]
}
```

### script_status — engine broadcasting script progress

Broadcast to **all** connected clients whenever a script starts, logs a message, or finishes.

| field | type | description |
|-------|------|-------------|
| `type` | string | `"script_status"` |
| `run_id` | string | Unique identifier for this script execution (32-character hex) |
| `name` | string | Script name |
| `status` | string | `"running"`, `"finished"`, `"error"`, or `"cancelled"` |
| `message` | string | Human-readable progress or result message |
| `progress` | number | Completion fraction in `[0.0, 1.0]` |

Lifecycle example for a successful slew:

```json
{ "type": "script_status", "run_id": "a1b2…", "name": "slew_and_track", "status": "running",  "message": "Script started",                        "progress": 0.0 }
{ "type": "script_status", "run_id": "a1b2…", "name": "slew_and_track", "status": "running",  "message": "Connecting to telescope…",               "progress": 0.0 }
{ "type": "script_status", "run_id": "a1b2…", "name": "slew_and_track", "status": "running",  "message": "Slewing to RA=5.0000h  DEC=20.0000°",   "progress": 0.0 }
{ "type": "script_status", "run_id": "a1b2…", "name": "slew_and_track", "status": "running",  "message": "Slewing…",                               "progress": 0.1 }
{ "type": "script_status", "run_id": "a1b2…", "name": "slew_and_track", "status": "running",  "message": "Slew complete — tracking at RA=5.0000h  DEC=20.0000°", "progress": 1.0 }
{ "type": "script_status", "run_id": "a1b2…", "name": "slew_and_track", "status": "finished", "message": "Script completed",                       "progress": 1.0 }
```

Scripts call `log(message, progress)` to emit intermediate `"running"` status messages. The engine emits `"running"` on start and a final `"finished"`, `"error"`, or `"cancelled"` on completion.

### script_error — error response

Sent to the requester when a `script_control` action fails (e.g. unknown script name, syntax error in uploaded script, missing field):

```json
{ "type": "script_error", "message": "Script 'unknown_script' not found" }
```
