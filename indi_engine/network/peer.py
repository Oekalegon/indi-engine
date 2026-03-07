"""Outbound connection from this engine to a peer engine.

A PeerConnection subscribes to a remote engine's socket server and forwards
received messages into the local engine's broadcast system (via
SocketServer.receive_peer_message), which handles provenance and filtering.

Two addressing modes are supported:

* **Direct** – ``host`` and ``port`` are given; the connection is made
  immediately without consulting mDNS discovery.
* **ID-based** – only ``engine_id`` is given; the connection waits until
  mDNS discovery resolves that ID to a host/port, then connects.  A
  ``discovery`` instance (``EngineDiscovery``) must be provided.
"""

import json
import logging
import socket
import threading
import time

logger = logging.getLogger(__name__)

_INITIAL_BACKOFF = 1.0
_MAX_BACKOFF = 60.0
_RESOLVE_POLL = 2.0  # seconds between discovery lookup retries


class PeerConnection:
    """Maintains an outbound subscription to a remote engine.

    Args:
        socket_server: Local SocketServer instance; receives forwarded messages.
        host: Hostname or IP for direct addressing (requires ``port`` too).
        port: TCP port for direct addressing.
        engine_id: Remote engine UUID for mDNS-based addressing (requires
                   ``discovery``).
        discovery: EngineDiscovery instance used to resolve ``engine_id``.
        devices: Optional list of device names to subscribe to. If None,
                 subscribes to all messages from the remote engine.
    """

    def __init__(self, socket_server, host: str = None, port: int = None,
                 engine_id: str = None, discovery=None, devices=None):
        if host and port:
            self._host = host
            self._port = port
            self._engine_id = engine_id  # informational only
            self._discovery = None
        elif engine_id and discovery:
            self._host = None
            self._port = None
            self._engine_id = engine_id
            self._discovery = discovery
        else:
            raise ValueError("PeerConnection requires either (host, port) or (engine_id, discovery)")

        self._socket_server = socket_server
        self._devices = devices  # None = all
        self._running = False
        self._thread: threading.Thread = None

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        if self._host:
            logger.info("PeerConnection started → %s:%d (devices=%s)", self._host, self._port, self._devices)
        else:
            logger.info("PeerConnection started → engine_id=%s (devices=%s, awaiting mDNS)", self._engine_id, self._devices)

    def stop(self) -> None:
        self._running = False

    def _resolve(self) -> tuple[str, int]:
        """Block until the target engine_id is found in mDNS discovery."""
        while self._running:
            entry = self._discovery.known_engines.get(self._engine_id)
            if entry:
                return entry["host"], entry["port"]
            logger.debug("PeerConnection waiting for mDNS resolution of engine_id=%s", self._engine_id)
            time.sleep(_RESOLVE_POLL)
        return None, None

    def _run(self) -> None:
        backoff = _INITIAL_BACKOFF
        while self._running:
            host, port = self._host, self._port
            if host is None:
                host, port = self._resolve()
                if not self._running:
                    break
            try:
                self._connect_and_read(host, port)
                backoff = _INITIAL_BACKOFF  # reset on clean disconnect
                # If ID-based, force re-resolve after disconnect (peer may have moved)
                if self._discovery:
                    host, port = None, None
            except Exception as e:
                if self._running:
                    logger.warning("PeerConnection %s:%d lost (%s), retrying in %.0fs", host, port, e, backoff)
                    time.sleep(backoff)
                    backoff = min(backoff * 2, _MAX_BACKOFF)

    def _connect_and_read(self, host: str, port: int) -> None:
        with socket.create_connection((host, port), timeout=10) as conn:
            conn.settimeout(None)  # blocking reads
            logger.info("PeerConnection connected to %s:%d", host, port)

            # Send subscribe message(s)
            if self._devices:
                for device in self._devices:
                    self._send(conn, {"type": "subscribe", "device": device})
            else:
                self._send(conn, {"type": "subscribe"})

            buf = b""
            while self._running:
                chunk = conn.recv(4096)
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
                        self._socket_server.receive_peer_message(msg)
                    except json.JSONDecodeError as e:
                        logger.warning("PeerConnection received invalid JSON: %s", e)

        logger.info("PeerConnection disconnected from %s:%d", host, port)

    def _send(self, conn: socket.socket, msg_dict: dict) -> None:
        conn.sendall((json.dumps(msg_dict) + "\n").encode("utf-8"))
