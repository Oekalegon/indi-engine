# INDI Engine

A non-GUI middleware layer between an [INDI](https://indilib.org) server and clients. It keeps device state in memory, exposes a JSON socket API for remote clients, and allows capturing sequences to continue when a client goes offline.

## Prerequisites

### System dependencies

**macOS (Homebrew)**
```bash
brew install libindi
```

**Ubuntu / Debian**
```bash
sudo apt install libindi-dev
```

### Python tooling

[uv](https://docs.astral.sh/uv/) is used for dependency management.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Installation

```bash
cd indi-engine
uv sync
```

## Running

```bash
uv run indi-engine
```

The engine connects to the INDI server on `localhost:7624` by default, keeps device state in memory, and listens for client connections on port `8624`.

If `server.manage` is `true` in the config (the default), the engine starts and stops `indiserver` automatically. Otherwise, start it yourself first:

```bash
indiserver -v indi_simulator_telescope indi_simulator_ccd
```

## CLI

`engine-cli` connects to a running engine over TCP and lets you watch events, query device state, and control the INDI server — including from a remote machine.

```bash
# Stream all engine events
uv run engine-cli watch

# Connect to a remote engine
uv run engine-cli --host 192.168.1.10 watch

# Filter to one device, or show raw JSON
uv run engine-cli watch --device "Telescope Simulator"
uv run engine-cli watch --raw

# List all known devices and their properties
uv run engine-cli devices

# Get the current value of a property
uv run engine-cli get "Telescope Simulator" EQUATORIAL_EOD_COORD

# Set a number property
uv run engine-cli set number "Telescope Simulator" EQUATORIAL_EOD_COORD RA=10.5 DEC=45.0

# Set a text property
uv run engine-cli set text "Device" PROPERTY ELEM=value

# Toggle a switch
uv run engine-cli set switch "Telescope Simulator" CONNECTION CONNECT

# Server control (works remotely)
uv run engine-cli server status
uv run engine-cli server start
uv run engine-cli server start --drivers indi_simulator_telescope indi_simulator_ccd
uv run engine-cli server stop
uv run engine-cli server restart
uv run engine-cli server restart --drivers indi_simulator_telescope
```

## Project structure

```
indi_engine/
├── main.py              # Entry point — starts server manager, connects client, runs loop
├── cli.py               # engine-cli — remote CLI for watch, devices, get, set, server control
├── indi/
│   ├── protocol/
│   │   ├── client.py    # PurePythonIndiClient — connects to indiserver, fires callbacks
│   │   ├── transport.py # TCP connection and reader thread
│   │   ├── parser.py    # INDI XML parser
│   │   └── properties.py# Typed property and element models
│   └── server.py        # ProcessServerManager / SystemdServerManager
└── server/
    ├── socket_server.py # JSON socket server — accepts clients, broadcasts events
    └── serializer.py    # IProperty → JSON dict serialization
```

## Configuration

Edit [config/main.yaml](config/main.yaml):

```yaml
indi:
  host: localhost
  port: 7624

server:
  # true  → engine starts/stops indiserver automatically
  # false → you manage indiserver yourself
  manage: true

  # How to manage indiserver when manage: true
  # process → spawn indiserver as a subprocess (default on systems without systemd)
  # systemd → use systemctl to manage the service
  # auto    → auto-detect at startup (check if systemd service is active)
  mode: auto

  # Process-mode settings
  verbose: false
  drivers:
    - indi_simulator_telescope
    - indi_simulator_ccd

  # Systemd-mode settings
  service_name: indiserver

engine:
  host: "0.0.0.0"
  port: 8624
  # Stable UUID for this engine. Set explicitly so other engines can reference
  # it by ID in their subscriptions. If omitted, a random UUID is generated
  # for this session only (not stable across restarts).
  id: "550e8400-e29b-41d4-a716-446655440000"
  name: "my-engine"     # "auto" uses the machine hostname
  # Capabilities advertised to peers and clients.
  # Plain string  → non-script capability
  # {id: script}  → capability backed by a specific script file
  capabilities:
    - indi_proxy
    - slew_telescope_and_track: slew_and_track.py
    - custom_scripts   # engine accepts arbitrary user-uploaded scripts
  subscriptions: []     # see "Multi-engine network" below
```

### Managing indiserver

**Process mode** (default): The engine spawns indiserver directly as a subprocess.

**Systemd mode**: The engine uses `systemctl` to manage a systemd unit. Useful on Linux servers where indiserver runs as a background service.

With `mode: auto`, the engine detects at startup which mode to use based on whether the service is running under systemd.

## Multi-engine network

Multiple engines can form a peer network. Each engine advertises itself via Bonjour/mDNS (`_indiengine._tcp.local.`) and can subscribe to message streams from other engines. Subscribed messages are forwarded to the engine's own clients with a `provenance` list that tracks the full chain of hops (INDI server → engine A → engine B → …).

### Relay engine

A relay engine has no INDI server connection — it subscribes to another engine and forwards its messages. Omit the `indi:` section entirely:

```yaml
# config/engine_b.yaml
engine:
  host: "0.0.0.0"
  port: 8625
  id: "6ba7b810-9dad-11d1-80b4-00c04fd430c8"
  name: "engine-b"
  capabilities:
    - indi_proxy
  subscriptions:
    - id: "550e8400-e29b-41d4-a716-446655440000"   # engine-a, resolved via mDNS
```

Start it with:
```bash
uv run indi-engine --config config/engine_b.yaml
```

### Subscription addressing

Two modes are supported in the `subscriptions` list:

**ID-based** (preferred) — engine ID resolved via mDNS; works regardless of the peer's IP address:
```yaml
subscriptions:
  - id: "550e8400-e29b-41d4-a716-446655440000"
    devices: ["Telescope Simulator"]   # optional — omit to subscribe to everything
```

**Direct** — host and port given explicitly; connects immediately without mDNS:
```yaml
subscriptions:
  - host: 192.168.1.10
    port: 8624
```

Both modes support an optional `devices` list to subscribe to specific devices only.

### Provenance

Every message broadcast by an engine carries a `provenance` field — an ordered list of identifiers showing where the message originated and which engines forwarded it:

```json
{
  "type": "set",
  "device": "Telescope Simulator",
  "property": "EQUATORIAL_EOD_COORD",
  "provenance": [
    "indi://localhost:7624",
    "550e8400-e29b-41d4-a716-446655440000",
    "6ba7b810-9dad-11d1-80b4-00c04fd430c8"
  ]
}
```

Engines use the provenance list to prevent forwarding loops: a message is dropped if the engine's own ID is already present.

### Discovery messages

Subscribed clients receive `engine_online` / `engine_offline` events as peers appear and disappear on the network. You can also query the known engine list at any time:

```json
// request
{"type": "engine_list_request"}

// response
{
  "type": "engine_list_response",
  "engines": [
    {"engine_id": "550e...", "name": "engine-a", "host": "192.168.1.5", "port": 8624, "capabilities": ["indi_proxy", "scripting"]}
  ]
}
```

## Protocol

The engine exposes a TCP socket on port `8624`. Messages are newline-delimited JSON. See [docs/protocol.md](docs/protocol.md) for the full message format reference including `def`, `set`, `new`, `message`, `server_control`, and `server_status`.
