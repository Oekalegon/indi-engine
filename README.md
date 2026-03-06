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
```

### Managing indiserver

**Process mode** (default): The engine spawns indiserver directly as a subprocess.

**Systemd mode**: The engine uses `systemctl` to manage a systemd unit. Useful on Linux servers where indiserver runs as a background service.

With `mode: auto`, the engine detects at startup which mode to use based on whether the service is running under systemd.

## Protocol

The engine exposes a TCP socket on port `8624`. Messages are newline-delimited JSON. See [docs/protocol.md](docs/protocol.md) for the full message format reference including `def`, `set`, `new`, `message`, `server_control`, and `server_status`.
