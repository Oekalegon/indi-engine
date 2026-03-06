#!/usr/bin/env python3
"""INDIEngine CLI — control the engine and INDI server remotely.

Usage:
    engine-cli watch
    engine-cli --host 192.168.1.10 watch
    engine-cli --host 192.168.1.10 watch --device "Telescope Simulator"
    engine-cli --host 192.168.1.10 watch --raw

    engine-cli server status
    engine-cli server start
    engine-cli server start --drivers indi_simulator_telescope indi_simulator_ccd
    engine-cli server stop
    engine-cli server restart
    engine-cli server restart --drivers indi_simulator_telescope

    engine-cli devices
    engine-cli get "Telescope Simulator" EQUATORIAL_EOD_COORD

    engine-cli set number "Telescope Simulator" EQUATORIAL_EOD_COORD RA=10.5 DEC=45.0
    engine-cli set text "Device" PROPERTY ELEM=value
    engine-cli set switch "Telescope Simulator" CONNECTION CONNECT
"""

import argparse
import json
import signal
import socket
import sys
import threading
import time
from datetime import datetime


# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"
RED    = "\033[31m"
BLUE   = "\033[34m"
MAGENTA = "\033[35m"

TYPE_COLOUR = {
    "def":           GREEN,
    "set":           CYAN,
    "message":       YELLOW,
    "server_status": MAGENTA,
}

DATA_TYPE_TAG = {
    "number": f"{CYAN}NUM{RESET}",
    "text":   f"{BLUE}TXT{RESET}",
    "switch": f"{YELLOW}SWT{RESET}",
    "light":  f"{GREEN}LGT{RESET}",
    "blob":   f"{RED}BLB{RESET}",
}


def _now():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def connect(host: str, port: int) -> socket.socket:
    try:
        sock = socket.create_connection((host, port), timeout=5)
        sock.settimeout(None)
        return sock
    except (ConnectionRefusedError, OSError) as e:
        print(f"{RED}Cannot connect to {host}:{port} — {e}{RESET}", file=sys.stderr)
        sys.exit(1)


def send_msg(sock: socket.socket, msg: dict) -> None:
    sock.sendall((json.dumps(msg) + "\n").encode("utf-8"))


def read_messages(sock: socket.socket, timeout: float = None):
    """Generator that yields parsed JSON dicts from the socket."""
    buf = b""
    deadline = time.monotonic() + timeout if timeout else None
    sock.settimeout(0.2)
    while True:
        if deadline and time.monotonic() > deadline:
            return
        try:
            chunk = sock.recv(4096)
        except socket.timeout:
            continue
        if not chunk:
            return
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            line = line.strip()
            if line:
                try:
                    yield json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    pass


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def fmt_msg(msg: dict) -> str:
    msg_type = msg.get("type", "?")
    colour   = TYPE_COLOUR.get(msg_type, DIM)
    label    = f"{colour}{BOLD}{msg_type:13}{RESET}"

    if msg_type in ("def", "set"):
        device    = msg.get("device", "?")
        prop      = msg.get("property", "?")
        data_type = msg.get("data_type", "?")
        state     = msg.get("state", "")
        tag       = DATA_TYPE_TAG.get(data_type, data_type)
        elems     = msg.get("elements", [])

        parts = []
        for e in elems:
            name = e.get("name", "?")
            val  = e.get("value")
            tgt  = e.get("target_value")
            if val is not None and tgt is not None and val != tgt:
                parts.append(f"{name}={val}{DIM}→{tgt}{RESET}")
            elif val is not None:
                parts.append(f"{name}={val}")
            else:
                parts.append(f"{name}({e.get('blob_format','')}{e.get('blob_size','')}b)")
        elems_str = "  ".join(parts)
        state_str = f"  {DIM}{state}{RESET}" if state else ""
        return (
            f"{_now()}  {label}  {device}/{prop}  {tag}{state_str}"
            + (f"  {elems_str}" if elems_str else "")
        )

    if msg_type == "message":
        device = msg.get("device")
        source = msg.get("source")
        text   = msg.get("message", "")
        who    = f"[{source}]" if source else f"[{device}]" if device else "[server]"
        return f"{_now()}  {label}  {who}  {text}"

    if msg_type == "server_status":
        running   = msg.get("running")
        drivers   = msg.get("drivers", [])
        connected = msg.get("indi_connected")
        r = f"{GREEN}running{RESET}" if running else f"{RED}stopped{RESET}"
        c = f"{GREEN}connected{RESET}" if connected else f"{RED}disconnected{RESET}"
        d = ", ".join(drivers) if drivers else "(none)"
        return f"{_now()}  {label}  indiserver={r}  indi={c}  drivers=[{d}]"

    return f"{_now()}  {label}  {json.dumps(msg)}"


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_watch(args):
    """Stream all engine messages."""
    sock = connect(args.host, args.port)
    print(f"{DIM}Connected to {args.host}:{args.port}"
          + (f"  device={args.device}" if args.device else "")
          + f"  — Ctrl-C to quit{RESET}\n")

    stop = threading.Event()

    def _sigint(sig, frame):
        print(f"\n{_now()}  Shutting down …")
        stop.set()

    signal.signal(signal.SIGINT, _sigint)
    sock.settimeout(1.0)
    buf = b""

    while not stop.is_set():
        try:
            chunk = sock.recv(4096)
        except socket.timeout:
            continue
        if not chunk:
            print(f"\n{_now()}  {RED}Server closed connection{RESET}")
            break
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line.decode("utf-8"))
                device = msg.get("device")
                if args.device and device and device != args.device:
                    continue
                if args.raw:
                    print(json.dumps(msg, indent=2))
                    print()
                else:
                    print(fmt_msg(msg))
            except json.JSONDecodeError:
                pass

    sock.close()


def cmd_server(args):
    """Send a server_control command and print the resulting server_status."""
    sock = connect(args.host, args.port)

    msg = {"type": "server_control", "action": args.action}
    if hasattr(args, "drivers") and args.drivers:
        msg["drivers"] = args.drivers

    send_msg(sock, msg)

    # Drain messages until we get a server_status response (or timeout)
    deadline = time.monotonic() + 15
    sock.settimeout(0.5)
    buf = b""
    while time.monotonic() < deadline:
        try:
            chunk = sock.recv(4096)
        except socket.timeout:
            continue
        if not chunk:
            break
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                response = json.loads(line.decode("utf-8"))
                if response.get("type") == "server_status":
                    print(fmt_msg(response))
                    sock.close()
                    return
            except json.JSONDecodeError:
                pass

    print(f"{RED}No server_status response received within timeout{RESET}", file=sys.stderr)
    sock.close()


def cmd_devices(args):
    """List all known devices by collecting the initial state burst."""
    sock = connect(args.host, args.port)
    devices = {}

    # Collect messages until there's a 0.5 s gap (state burst complete)
    sock.settimeout(0.5)
    buf = b""
    while True:
        try:
            chunk = sock.recv(4096)
        except socket.timeout:
            break
        if not chunk:
            break
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line.decode("utf-8"))
                if msg.get("type") == "def":
                    device = msg.get("device")
                    if device:
                        devices.setdefault(device, set()).add(msg.get("property", "?"))
            except json.JSONDecodeError:
                pass

    sock.close()

    if not devices:
        print("No devices found.")
        return

    for device, props in sorted(devices.items()):
        print(f"{BOLD}{device}{RESET}  ({len(props)} properties)")
        for p in sorted(props):
            print(f"    {DIM}{p}{RESET}")


def cmd_get(args):
    """Get the current value of a specific property."""
    sock = connect(args.host, args.port)

    sock.settimeout(0.5)
    buf = b""
    found = False
    while True:
        try:
            chunk = sock.recv(4096)
        except socket.timeout:
            break
        if not chunk:
            break
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line.decode("utf-8"))
                if (msg.get("type") in ("def", "set")
                        and msg.get("device") == args.device
                        and msg.get("property") == args.property):
                    print(fmt_msg(msg))
                    found = True
            except json.JSONDecodeError:
                pass

    sock.close()
    if not found:
        print(f"{RED}Property {args.device}/{args.property} not found{RESET}", file=sys.stderr)
        sys.exit(1)


def cmd_set(args):
    """Send a new command to set a property value."""
    sock = connect(args.host, args.port)

    data_type = args.set_type  # "number", "text", "switch"

    if data_type == "switch":
        # args.element is a single element name to set On
        elements = [{"name": args.element, "value": "On"}]
    else:
        # args.assignments is a list of "NAME=VALUE" strings
        elements = []
        for assignment in args.assignments:
            if "=" not in assignment:
                print(f"{RED}Invalid element assignment '{assignment}': expected NAME=VALUE{RESET}",
                      file=sys.stderr)
                sys.exit(1)
            name, _, value = assignment.partition("=")
            elements.append({
                "name": name.strip(),
                "value": float(value) if data_type == "number" else value.strip(),
            })

    msg = {
        "type": "new",
        "device": args.device,
        "property": args.property,
        "data_type": data_type,
        "elements": elements,
    }

    send_msg(sock, msg)
    print(f"Sent: {json.dumps(msg, indent=2)}")
    sock.close()


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="engine-cli",
        description="INDIEngine remote CLI — control the engine and INDI server.",
    )
    parser.add_argument("--host", default="localhost", help="Engine host (default: localhost)")
    parser.add_argument("--port", default=8624, type=int, help="Engine port (default: 8624)")

    sub = parser.add_subparsers(dest="command", required=True)

    # --- watch ---
    p_watch = sub.add_parser("watch", help="Stream all engine messages")
    p_watch.add_argument("--device", default=None, help="Filter to this device")
    p_watch.add_argument("--raw", action="store_true", help="Print raw JSON")

    # --- server ---
    p_server = sub.add_parser("server", help="Control the INDI server")
    server_sub = p_server.add_subparsers(dest="action", required=True)

    server_sub.add_parser("status", help="Show server status")
    server_sub.add_parser("stop",   help="Stop indiserver")

    p_start = server_sub.add_parser("start", help="Start indiserver")
    p_start.add_argument("--drivers", nargs="+", metavar="DRIVER",
                         help="Driver names to load (overrides config)")

    p_restart = server_sub.add_parser("restart", help="Restart indiserver")
    p_restart.add_argument("--drivers", nargs="+", metavar="DRIVER",
                           help="Driver names to load after restart (overrides config)")

    # --- devices ---
    sub.add_parser("devices", help="List known devices and their properties")

    # --- get ---
    p_get = sub.add_parser("get", help="Get the current value of a property")
    p_get.add_argument("device",   help="Device name")
    p_get.add_argument("property", help="Property name")

    # --- set ---
    p_set = sub.add_parser("set", help="Set a property value")
    set_sub = p_set.add_subparsers(dest="set_type", required=True)

    p_set_num = set_sub.add_parser("number", help="Set a number property")
    p_set_num.add_argument("device",      help="Device name")
    p_set_num.add_argument("property",    help="Property name")
    p_set_num.add_argument("assignments", nargs="+", metavar="ELEM=VALUE",
                           help="Element assignments, e.g. RA=10.5 DEC=45.0")

    p_set_txt = set_sub.add_parser("text", help="Set a text property")
    p_set_txt.add_argument("device",      help="Device name")
    p_set_txt.add_argument("property",    help="Property name")
    p_set_txt.add_argument("assignments", nargs="+", metavar="ELEM=VALUE")

    p_set_sw = set_sub.add_parser("switch", help="Set a switch element to On")
    p_set_sw.add_argument("device",   help="Device name")
    p_set_sw.add_argument("property", help="Property name")
    p_set_sw.add_argument("element",  help="Element name to set On")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "watch":
        cmd_watch(args)
    elif args.command == "server":
        cmd_server(args)
    elif args.command == "devices":
        cmd_devices(args)
    elif args.command == "get":
        cmd_get(args)
    elif args.command == "set":
        cmd_set(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
