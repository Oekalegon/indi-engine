"""Unit tests for SocketServer: server_control routing and server_status responses.

Uses mock server manager and INDI client — no real indiserver required.
All tests run on TEST_PORT (18624) to avoid clashing with a live engine on 8624.
"""

import json
import socket
import time
from unittest.mock import MagicMock, patch

import pytest

from indi_engine.indi.protocol.client import PurePythonIndiClient
from indi_engine.server.socket_server import SocketServer

TEST_PORT = 18624


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_manager(running=True, drivers=None):
    mgr = MagicMock()
    mgr.is_running.return_value = running
    mgr.drivers = list(drivers or ["indi_simulator_telescope", "indi_simulator_ccd"])
    return mgr


def _mock_indi_client(connected=True):
    client = MagicMock()
    client.isServerConnected.return_value = connected
    client._devices = {}
    return client


def _connect(port=TEST_PORT, timeout=5.0):
    sock = socket.create_connection(("localhost", port), timeout=timeout)
    sock.settimeout(3.0)
    return sock


def _drain_until(sock, predicate, timeout=5.0):
    """Read JSON messages until predicate(msg) returns True. Returns matching msg."""
    buf = b""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            chunk = sock.recv(4096)
        except socket.timeout:
            continue
        if not chunk:
            raise ConnectionError("Socket closed unexpectedly")
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            line = line.strip()
            if not line:
                continue
            msg = json.loads(line.decode("utf-8"))
            if predicate(msg):
                return msg
    raise TimeoutError("Expected message not received within timeout")


def _send(sock, msg):
    sock.sendall((json.dumps(msg) + "\n").encode("utf-8"))


def _is_server_status(msg):
    return msg.get("type") == "server_status"


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def server():
    s = SocketServer(host="localhost", port=TEST_PORT)
    s.start()
    yield s
    s.stop()


# ---------------------------------------------------------------------------
# server_control: status
# ---------------------------------------------------------------------------

def test_status_returns_server_status(server):
    server.set_server_manager(_mock_manager(running=True, drivers=["indi_simulator_telescope"]))
    server.set_indi_client(_mock_indi_client(connected=True))

    sock = _connect()
    _send(sock, {"type": "server_control", "action": "status"})
    msg = _drain_until(sock, _is_server_status)
    sock.close()

    assert msg["running"] is True
    assert msg["indi_connected"] is True
    assert msg["drivers"] == ["indi_simulator_telescope"]


def test_status_without_server_manager_returns_defaults(server):
    server.set_indi_client(_mock_indi_client(connected=False))

    sock = _connect()
    _send(sock, {"type": "server_control", "action": "status"})
    msg = _drain_until(sock, _is_server_status)
    sock.close()

    assert msg["running"] is False
    assert msg["drivers"] == []


# ---------------------------------------------------------------------------
# server_control: stop
# ---------------------------------------------------------------------------

def test_stop_calls_manager_stop(server):
    mgr = _mock_manager(running=False)
    server.set_server_manager(mgr)
    server.set_indi_client(_mock_indi_client(connected=False))

    sock = _connect()
    _send(sock, {"type": "server_control", "action": "stop"})
    msg = _drain_until(sock, _is_server_status)
    sock.close()

    mgr.stop.assert_called_once()
    assert msg["running"] is False


def test_stop_disconnects_indi_client(server):
    mgr = _mock_manager()
    client = _mock_indi_client()
    server.set_server_manager(mgr)
    server.set_indi_client(client)

    sock = _connect()
    _send(sock, {"type": "server_control", "action": "stop"})
    _drain_until(sock, _is_server_status)
    sock.close()

    client.disconnectServer.assert_called_once()


# ---------------------------------------------------------------------------
# server_control: start
# ---------------------------------------------------------------------------

def test_start_calls_manager_start(server):
    mgr = _mock_manager(running=False)
    server.set_server_manager(mgr)
    server.set_indi_client(_mock_indi_client())

    sock = _connect()
    _send(sock, {"type": "server_control", "action": "start"})
    _drain_until(sock, _is_server_status)
    sock.close()

    mgr.start.assert_called_once()


def test_start_when_already_running_skips_start(server):
    mgr = _mock_manager(running=True)
    server.set_server_manager(mgr)
    server.set_indi_client(_mock_indi_client())

    sock = _connect()
    _send(sock, {"type": "server_control", "action": "start"})
    _drain_until(sock, _is_server_status)
    sock.close()

    mgr.start.assert_not_called()


def test_start_with_drivers_overrides_driver_list(server):
    mgr = _mock_manager(running=False)
    server.set_server_manager(mgr)
    server.set_indi_client(_mock_indi_client())

    sock = _connect()
    _send(sock, {"type": "server_control", "action": "start",
                 "drivers": ["indi_simulator_telescope"]})
    _drain_until(sock, _is_server_status)
    sock.close()

    assert mgr._drivers == ["indi_simulator_telescope"]
    mgr.start.assert_called_once()


def test_start_calls_reconnect_callback(server):
    mgr = _mock_manager(running=False)
    server.set_server_manager(mgr)
    server.set_indi_client(_mock_indi_client())
    callback = MagicMock()
    server.set_reconnect_callback(callback)

    sock = _connect()
    _send(sock, {"type": "server_control", "action": "start"})
    _drain_until(sock, _is_server_status)
    sock.close()

    callback.assert_called_once()


# ---------------------------------------------------------------------------
# server_control: restart
# ---------------------------------------------------------------------------

def test_restart_calls_manager_restart(server):
    mgr = _mock_manager()
    server.set_server_manager(mgr)
    server.set_indi_client(_mock_indi_client())

    sock = _connect()
    _send(sock, {"type": "server_control", "action": "restart"})
    _drain_until(sock, _is_server_status)
    sock.close()

    mgr.restart.assert_called_once_with(None)


def test_restart_with_drivers_passes_drivers(server):
    mgr = _mock_manager()
    server.set_server_manager(mgr)
    server.set_indi_client(_mock_indi_client())

    drivers = ["indi_simulator_telescope"]
    sock = _connect()
    _send(sock, {"type": "server_control", "action": "restart", "drivers": drivers})
    _drain_until(sock, _is_server_status)
    sock.close()

    mgr.restart.assert_called_once_with(drivers)


def test_restart_disconnects_indi_client(server):
    mgr = _mock_manager()
    client = _mock_indi_client()
    server.set_server_manager(mgr)
    server.set_indi_client(client)

    sock = _connect()
    _send(sock, {"type": "server_control", "action": "restart"})
    _drain_until(sock, _is_server_status)
    sock.close()

    client.disconnectServer.assert_called_once()


def test_restart_calls_reconnect_callback(server):
    mgr = _mock_manager()
    server.set_server_manager(mgr)
    server.set_indi_client(_mock_indi_client())
    callback = MagicMock()
    server.set_reconnect_callback(callback)

    sock = _connect()
    _send(sock, {"type": "server_control", "action": "restart"})
    _drain_until(sock, _is_server_status)
    sock.close()

    callback.assert_called_once()


# ---------------------------------------------------------------------------
# Unknown action
# ---------------------------------------------------------------------------

def test_unknown_action_still_returns_server_status(server):
    server.set_server_manager(_mock_manager())
    server.set_indi_client(_mock_indi_client())

    sock = _connect()
    _send(sock, {"type": "server_control", "action": "self_destruct"})
    msg = _drain_until(sock, _is_server_status)
    sock.close()

    assert msg["type"] == "server_status"


# ---------------------------------------------------------------------------
# Broadcast to all clients
# ---------------------------------------------------------------------------

def test_server_status_broadcast_to_observer_clients(server):
    """The server_status also reaches clients that did not send the command."""
    server.set_server_manager(_mock_manager())
    server.set_indi_client(_mock_indi_client())

    requester = _connect()
    observer = _connect()

    _send(requester, {"type": "server_control", "action": "status"})

    msg_requester = _drain_until(requester, _is_server_status)
    msg_observer  = _drain_until(observer,  _is_server_status)

    requester.close()
    observer.close()

    assert msg_requester["type"] == "server_status"
    assert msg_observer["type"] == "server_status"


# ---------------------------------------------------------------------------
# Device cache cleared on reconnect
# ---------------------------------------------------------------------------

def test_connect_server_clears_device_cache():
    """_devices must be empty at the start of each new INDI session."""
    client = PurePythonIndiClient("localhost", 7624)
    client._devices["StaleDevice"] = MagicMock()

    with (
        patch.object(client._transport, "connect"),
        patch.object(client, "_start_message_loop"),
        patch.object(client, "serverConnected"),
    ):
        client.connectServer()

    assert "StaleDevice" not in client._devices
