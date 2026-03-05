#!/usr/bin/env python3
"""INDI server monitor — connects and prints all events to stdout.

Usage:
    uv run examples/monitor.py
    uv run examples/monitor.py --host 192.168.1.10 --port 7624
    uv run examples/monitor.py --device "CCD Simulator"
    uv run examples/monitor.py --verbose
"""

import argparse
import signal
import sys
import time
from datetime import datetime

from indi_engine.indi.protocol.client import PurePythonIndiClient
from indi_engine.indi.protocol.constants import IndiPropertyType, IndiPropertyState


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"
RED    = "\033[31m"
BLUE   = "\033[34m"

STATE_COLOUR = {
    IndiPropertyState.OK:    GREEN,
    IndiPropertyState.BUSY:  YELLOW,
    IndiPropertyState.ALERT: RED,
    IndiPropertyState.IDLE:  DIM,
}


def _now():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def _state(prop):
    colour = STATE_COLOUR.get(prop.getState(), "")
    return f"{colour}{prop.getState().value}{RESET}"


def _elements(prop, verbose=False):
    elems = prop.getElements()
    if not elems:
        return ""
    parts = []
    for e in elems:
        val = e.getValue()
        if prop.getType() == IndiPropertyType.NUMBER and e.getFormat():
            try:
                val = e.getFormat() % float(val)
            except (ValueError, TypeError):
                pass
        parts.append(f"{e.getName()}={str(val).strip()}")
    sep = "\n        " if verbose and len(parts) > 3 else "  "
    return sep.join(parts)


def _prop_type_tag(prop):
    colours = {
        IndiPropertyType.NUMBER: CYAN,
        IndiPropertyType.TEXT:   BLUE,
        IndiPropertyType.SWITCH: YELLOW,
        IndiPropertyType.LIGHT:  GREEN,
        IndiPropertyType.BLOB:   RED,
    }
    c = colours.get(prop.getType(), "")
    tag = prop.getType().value[:3].upper()
    return f"{c}{tag}{RESET}"


# ---------------------------------------------------------------------------
# Monitor client
# ---------------------------------------------------------------------------

class MonitorClient(PurePythonIndiClient):

    def __init__(self, host, port, device_filter=None, verbose=False):
        super().__init__(host, port)
        self._filter = device_filter
        self._verbose = verbose
        self._setup()

    def _setup(self):
        self.serverConnected    = self._on_connected
        self.serverDisconnected = self._on_disconnected
        self.newDevice          = self._on_new_device
        self.removeDevice       = self._on_remove_device
        self.newProperty        = self._on_new_property
        self.updateProperty     = self._on_update_property
        self.removeProperty     = self._on_remove_property
        self.newBLOB            = self._on_blob
        self.newMessage         = self._on_message
        self.newUniversalMessage = self._on_universal_message

    def _skip(self, device_name):
        return self._filter and device_name != self._filter

    # --- connection ---

    def _on_connected(self):
        print(f"{_now()}  {BOLD}{GREEN}Connected{RESET} to {self.host}:{self.port}")

    def _on_disconnected(self, code):
        label = "clean disconnect" if code == 0 else f"error (code {code})"
        print(f"{_now()}  {BOLD}{RED}Disconnected{RESET}  {label}")

    # --- devices ---

    def _on_new_device(self, device):
        if self._skip(device.getDeviceName()):
            return
        print(f"{_now()}  {BOLD}+ device{RESET}  {device.getDeviceName()}")

    def _on_remove_device(self, device):
        if self._skip(device.getDeviceName()):
            return
        print(f"{_now()}  {BOLD}- device{RESET}  {device.getDeviceName()}")

    # --- properties ---

    def _on_new_property(self, prop):
        if self._skip(prop.getDeviceName()):
            return
        elems = _elements(prop, self._verbose)
        group = f"  {DIM}[{prop.getGroupName()}]{RESET}" if self._verbose and prop.getGroupName() else ""
        print(
            f"{_now()}  {BOLD}+ prop{RESET}  "
            f"{prop.getDeviceName()}/{prop.getName()}  "
            f"{_prop_type_tag(prop)}  {_state(prop)}{group}"
            + (f"  {elems}" if elems else "")
        )

    def _on_update_property(self, prop):
        if self._skip(prop.getDeviceName()):
            return
        elems = _elements(prop, self._verbose)
        print(
            f"{_now()}  {BOLD}~ prop{RESET}  "
            f"{prop.getDeviceName()}/{prop.getName()}  "
            f"{_prop_type_tag(prop)}  {_state(prop)}"
            + (f"  {elems}" if elems else "")
        )

    def _on_remove_property(self, prop):
        if self._skip(prop.getDeviceName()):
            return
        print(
            f"{_now()}  {BOLD}- prop{RESET}  "
            f"{prop.getDeviceName()}/{prop.getName()}"
        )

    # --- BLOBs ---

    def _on_blob(self, prop):
        if self._skip(prop.getDeviceName()):
            return
        for elem in prop:
            size = elem.getbloblen()
            fmt  = elem.getblobformat()
            print(
                f"{_now()}  {BOLD}{RED}BLOB{RESET}  "
                f"{prop.getDeviceName()}/{prop.getName()}/{elem.getName()}  "
                f"{fmt}  {size:,} bytes"
            )

    # --- messages ---

    def _on_message(self, device, text):
        if self._skip(device.getDeviceName()):
            return
        print(f"{_now()}  {BOLD}msg{RESET}  [{device.getDeviceName()}]  {text}")

    def _on_universal_message(self, text):
        print(f"{_now()}  {BOLD}msg{RESET}  [server]  {text}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Connect to an INDI server and print all events."
    )
    parser.add_argument("--host",    default="localhost", help="INDI server host (default: localhost)")
    parser.add_argument("--port",    default=7624, type=int, help="INDI server port (default: 7624)")
    parser.add_argument("--device",  default=None, help="Watch only this device (default: all)")
    parser.add_argument("--verbose", action="store_true", help="Show element details and group names")
    args = parser.parse_args()

    client = MonitorClient(
        host=args.host,
        port=args.port,
        device_filter=args.device,
        verbose=args.verbose,
    )

    # Graceful Ctrl-C
    def _sigint(sig, frame):
        print(f"\n{_now()}  Shutting down...")
        client.disconnectServer()
        sys.exit(0)

    signal.signal(signal.SIGINT, _sigint)

    try:
        client.connectServer()
    except Exception as e:
        print(f"Could not connect to {args.host}:{args.port} — {e}", file=sys.stderr)
        sys.exit(1)

    client.watchDevice(args.device or "")

    print(f"{DIM}Watching {'device: ' + args.device if args.device else 'all devices'}  —  Ctrl-C to quit{RESET}\n")

    # Keep main thread alive while reader thread runs
    while client.isServerConnected():
        time.sleep(0.5)


if __name__ == "__main__":
    main()
