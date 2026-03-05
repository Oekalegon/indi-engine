# INDI Engine

A non-GUI middleware layer between an [INDI](https://indilib.org) server and clients. It keeps device state in memory and allows capturing sequences to continue when a client goes offline.

## Prerequisites

### System dependencies

INDI Engine uses [pyindi-client](https://github.com/indilib/pyindi-client), a Python wrapper around `libindi`. The native library must be installed before you can run the engine.

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

The engine connects to the INDI server on `localhost:7624` by default and logs all device and property events to stdout. Stop it with `Ctrl+C`.

If `server.manage` is `true` in the config, the engine starts and stops `indiserver` automatically. Otherwise, start it yourself first:

```bash
indiserver -v indi_simulator_telescope indi_simulator_ccd
```

## Project structure

```
indi_engine/
├── main.py              # Entry point — starts server manager, connects client, runs loop
├── indi/
│   ├── client.py        # IndiClient — receives device/property messages from INDI
│   └── server.py        # IndiServerManager — starts/stops indiserver subprocess
├── state/
│   └── manager.py       # DeviceStateManager — keeps current device/property state
├── server/
│   └── socket_server.py # (stub) JSON socket server for client communication
└── actions/
    └── __init__.py      # (stub) Action system for telescope control sequences
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
```

### Managing indiserver

**Process mode** (default): The engine spawns indiserver directly as a subprocess.
```bash
uv run indi-engine
```

**Systemd mode**: The engine uses `systemctl` to manage a systemd unit. Useful on Linux servers where indiserver runs as a background service.
```bash
# Create a systemd unit (if not already installed)
sudo systemctl enable indiserver

# Start the engine (it will use systemctl to manage the service)
uv run indi-engine
```

With `mode: auto`, the engine detects at startup which mode to use based on whether the service is running under systemd.

### Drivers

Drivers can be added or removed at runtime via `ProcessServerManager.add_driver()` / `remove_driver()` or `SystemdServerManager.add_driver()` / `remove_driver()` — the server restarts automatically with the updated driver list.
