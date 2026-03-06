#!/usr/bin/env python3
"""Engine client — connects to the INDIEngine socket server and prints all messages.

Usage:
    uv run examples/engine_client.py
    uv run examples/engine_client.py --host 192.168.1.10 --port 8624
    uv run examples/engine_client.py --device "Telescope Simulator"
    uv run examples/engine_client.py --send '{"type":"new","device":"Telescope Simulator","property":"EQUATORIAL_EOD_COORD","data_type":"number","elements":[{"name":"RA","value":10.5},{"name":"DEC","value":45.0}]}'
"""

import argparse
import json
import signal
import socket
import sys
import threading
from datetime import datetime


RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"
RED    = "\033[31m"
BLUE   = "\033[34m"

TYPE_COLOUR = {
    "def":     GREEN,
    "set":     CYAN,
    "message": YELLOW,
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


def _format_msg(msg: dict, device_filter: str | None) -> str | None:
    msg_type = msg.get("type", "?")
    device   = msg.get("device")

    if device_filter and device and device != device_filter:
        return None

    colour = TYPE_COLOUR.get(msg_type, DIM)
    label  = f"{colour}{BOLD}{msg_type:7}{RESET}"

    if msg_type in ("def", "set"):
        prop      = msg.get("property", "?")
        data_type = msg.get("data_type", "?")
        state     = msg.get("state", "")
        tag       = DATA_TYPE_TAG.get(data_type, data_type)
        elems     = msg.get("elements", [])

        elem_parts = []
        for e in elems:
            name = e.get("name", "?")
            val  = e.get("value")
            tgt  = e.get("target_value")
            if val is not None and tgt is not None and val != tgt:
                elem_parts.append(f"{name}={val} {DIM}→{tgt}{RESET}")
            elif val is not None:
                elem_parts.append(f"{name}={val}")
            else:
                # blob or other element without value
                fmt = e.get("blob_format", "")
                sz  = e.get("blob_size", "")
                elem_parts.append(f"{name} {fmt} {sz}b".strip())

        elems_str = "  ".join(elem_parts)
        state_str = f"  {DIM}{state}{RESET}" if state else ""
        return (
            f"{_now()}  {label}  {device}/{prop}  {tag}{state_str}"
            + (f"  {elems_str}" if elems_str else "")
        )

    if msg_type == "message":
        text   = msg.get("message", "")
        source = msg.get("source")
        who    = f"[{source}]" if source else f"[{device}]" if device else "[server]"
        return f"{_now()}  {label}  {who}  {text}"

    # Fallback: dump raw JSON
    return f"{_now()}  {label}  {json.dumps(msg)}"


def read_loop(sock: socket.socket, device_filter: str | None, stop_event: threading.Event, raw: bool = False):
    buf = b""
    sock.settimeout(1.0)
    while not stop_event.is_set():
        try:
            chunk = sock.recv(4096)
        except socket.timeout:
            continue
        if not chunk:
            print(f"\n{_now()}  {RED}Server closed connection{RESET}")
            stop_event.set()
            break
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line.decode("utf-8"))
                if raw:
                    device = msg.get("device")
                    if not device_filter or device == device_filter:
                        print(json.dumps(msg, indent=2))
                        print()
                else:
                    formatted = _format_msg(msg, device_filter)
                    if formatted:
                        print(formatted)
            except json.JSONDecodeError:
                print(f"{_now()}  {RED}Invalid JSON{RESET}: {line!r}")


def main():
    parser = argparse.ArgumentParser(
        description="Connect to the INDIEngine socket server and print all messages."
    )
    parser.add_argument("--host",   default="localhost", help="Engine host (default: localhost)")
    parser.add_argument("--port",   default=8624, type=int, help="Engine port (default: 8624)")
    parser.add_argument("--device", default=None, help="Filter output to this device")
    parser.add_argument("--raw",    action="store_true", help="Print raw pretty-printed JSON instead of formatted output")
    parser.add_argument("--send",   default=None, metavar="JSON",
                        help="Send a single JSON command and exit")
    args = parser.parse_args()

    try:
        sock = socket.create_connection((args.host, args.port))
    except ConnectionRefusedError:
        print(f"Could not connect to {args.host}:{args.port} — is the engine running?",
              file=sys.stderr)
        sys.exit(1)

    if args.send:
        # One-shot command mode
        try:
            msg = json.loads(args.send)
        except json.JSONDecodeError as e:
            print(f"Invalid JSON: {e}", file=sys.stderr)
            sys.exit(1)
        sock.sendall((json.dumps(msg) + "\n").encode("utf-8"))
        print(f"Sent: {json.dumps(msg)}")
        sock.close()
        return

    stop_event = threading.Event()

    def _sigint(sig, frame):
        print(f"\n{_now()}  Shutting down …")
        stop_event.set()

    signal.signal(signal.SIGINT, _sigint)

    print(f"{DIM}Connected to {args.host}:{args.port}"
          + (f"  filtering device: {args.device}" if args.device else "")
          + f"  —  Ctrl-C to quit{RESET}\n")

    read_loop(sock, args.device, stop_event, raw=args.raw)
    sock.close()


if __name__ == "__main__":
    main()
