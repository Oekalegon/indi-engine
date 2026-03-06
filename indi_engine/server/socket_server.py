"""JSON socket server for engine↔client communication.

Clients connect over TCP and exchange newline-delimited JSON messages:
  - Engine → client: "def", "set", "message", and "server_status" messages
  - Client → engine: "new" and "server_control" commands

Framing: each message is a single JSON object followed by a newline character.
"""

import json
import logging
import select
import socket
import threading
from typing import Optional

from indi_engine.indi.protocol.client import PurePythonIndiClient
from indi_engine.indi.protocol.properties import IProperty, IPropertyElement
from indi_engine.indi.protocol.constants import IndiPropertyType, IndiPropertyPerm
from indi_engine.indi.protocol.errors import IndiDisconnectedError
from indi_engine.server.serializer import serialize_property

logger = logging.getLogger(__name__)


class SocketServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 8624):
        self.host = host
        self.port = port
        self._indi_client: Optional[PurePythonIndiClient] = None
        self._server_manager = None
        self._reconnect_callback = None
        self._script_runner = None
        self._clients: list = []
        self._clients_lock = threading.Lock()
        self._server_socket: Optional[socket.socket] = None
        self._running = False
        self._accept_thread: Optional[threading.Thread] = None

    def set_indi_client(self, client: PurePythonIndiClient) -> None:
        """Set the INDI client used to forward 'new' commands."""
        self._indi_client = client

    def set_server_manager(self, manager) -> None:
        """Set the INDI server manager used to handle server_control commands."""
        self._server_manager = manager

    def set_reconnect_callback(self, callback) -> None:
        """Set a callable() that reconnects the INDI client after a server restart."""
        self._reconnect_callback = callback

    def set_script_runner(self, runner) -> None:
        """Set the ScriptRunner used to handle script_control commands."""
        self._script_runner = runner

    def start(self) -> None:
        """Bind, listen, and start accepting connections in a background thread."""
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind((self.host, self.port))
        self._server_socket.listen(10)
        self._server_socket.settimeout(1.0)
        self._running = True
        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._accept_thread.start()
        logger.info("Engine socket server listening on %s:%d", self.host, self.port)

    def stop(self) -> None:
        """Stop the server and close all client connections."""
        self._running = False
        if self._server_socket:
            try:
                self._server_socket.close()
            except OSError:
                pass
        with self._clients_lock:
            for conn in self._clients:
                try:
                    conn.close()
                except OSError:
                    pass
            self._clients.clear()

    def _accept_loop(self) -> None:
        while self._running:
            try:
                conn, addr = self._server_socket.accept()
                logger.info("Client connected from %s:%d", addr[0], addr[1])
                with self._clients_lock:
                    self._clients.append(conn)
                self._send_current_state(conn)
                t = threading.Thread(target=self._handle_client, args=(conn,), daemon=True)
                t.start()
            except socket.timeout:
                continue
            except OSError:
                break

    def _send_current_state(self, conn: socket.socket) -> None:
        """Send all currently known properties to a newly connected client."""
        if not self._indi_client:
            return
        for device in self._indi_client._devices.values():
            for prop in device.properties.values():
                try:
                    data = (json.dumps(serialize_property(prop, "def")) + "\n").encode("utf-8")
                    conn.sendall(data)
                except OSError:
                    return

    def _handle_client(self, conn: socket.socket) -> None:
        # Use select() rather than settimeout() so that conn stays in blocking
        # mode for sendall() calls in broadcast() — a 1-second socket timeout
        # on sendall would silently drop messages to slow readers.
        buf = b""
        try:
            while self._running:
                ready, _, _ = select.select([conn], [], [], 1.0)
                if not ready:
                    continue
                try:
                    chunk = conn.recv(4096)
                except OSError:
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
                        self._handle_command(msg, conn)
                    except json.JSONDecodeError as e:
                        logger.warning("Received invalid JSON from client: %s", e)
        except OSError:
            pass
        finally:
            with self._clients_lock:
                if conn in self._clients:
                    self._clients.remove(conn)
            try:
                conn.close()
            except OSError:
                pass
            logger.info("Client disconnected")

    def _handle_command(self, msg: dict, conn: socket.socket) -> None:
        msg_type = msg.get("type")
        if msg_type == "server_control":
            threading.Thread(target=self._handle_server_control, args=(msg, conn), daemon=True).start()
            return
        if msg_type == "script_control":
            threading.Thread(target=self._handle_script_control, args=(msg, conn), daemon=True).start()
            return
        if msg_type != "new":
            logger.debug("Ignoring unknown message type: %s", msg_type)
            return

        if not self._indi_client:
            logger.warning("Received 'new' command but no INDI client is set")
            return

        data_type = msg.get("data_type")
        if not data_type or not msg.get("device") or not msg.get("property"):
            logger.warning("Malformed 'new' command: %s", msg)
            return

        try:
            prop = self._build_iproperty_from_command(msg)
        except Exception as e:
            logger.warning("Failed to build IProperty from command: %s", e)
            return

        try:
            if data_type == "number":
                self._indi_client.sendNewNumber(prop)
            elif data_type == "text":
                self._indi_client.sendNewText(prop)
            elif data_type == "switch":
                self._indi_client.sendNewSwitch(prop)
            else:
                logger.warning("Unsupported data_type in 'new' command: %s", data_type)
        except IndiDisconnectedError:
            logger.warning("Cannot forward 'new' command: INDI client not connected")

    def _handle_server_control(self, msg: dict, requester: socket.socket) -> None:
        """Handle a server_control command (runs in its own thread)."""
        action = msg.get("action")
        drivers = msg.get("drivers")  # optional list of driver names

        if not self._server_manager:
            logger.warning("Received server_control but no server manager is set")
            self._send_server_status(requester)
            return

        try:
            if action == "status":
                pass  # fall through to send status

            elif action == "start":
                if self._server_manager.is_running():
                    logger.info("server_control start: server already running")
                else:
                    if drivers is not None:
                        self._server_manager._drivers = list(drivers)
                    self._server_manager.start()
                    if self._reconnect_callback:
                        self._reconnect_callback()

            elif action == "stop":
                if self._indi_client:
                    self._indi_client.disconnectServer()
                self._server_manager.stop()

            elif action == "restart":
                if self._indi_client:
                    self._indi_client.disconnectServer()
                self._server_manager.restart(drivers)
                if self._reconnect_callback:
                    self._reconnect_callback()

            else:
                logger.warning("Unknown server_control action: %s", action)
                self._send_server_status(requester)
                return

        except Exception as e:
            logger.error("server_control %s failed: %s", action, e)

        self._send_server_status(requester)
        self._broadcast_server_status(exclude=requester)

    def _build_server_status(self) -> dict:
        """Return a server_status dict reflecting current state."""
        return {
            "type": "server_status",
            "running": self._server_manager.is_running() if self._server_manager else False,
            "drivers": self._server_manager.drivers if self._server_manager else [],
            "indi_connected": self._indi_client.isServerConnected() if self._indi_client else False,
        }

    def _send_server_status(self, conn: socket.socket) -> None:
        """Send a server_status message directly to a single client."""
        try:
            data = (json.dumps(self._build_server_status()) + "\n").encode("utf-8")
            conn.sendall(data)
        except OSError as e:
            logger.debug("Could not send server_status to client: %s", e)

    def _broadcast_server_status(self, exclude: socket.socket = None) -> None:
        """Broadcast the current server and INDI connection status to all clients."""
        self.broadcast(self._build_server_status(), exclude=exclude)

    def broadcast(self, msg_dict: dict, exclude: socket.socket = None) -> None:
        """Serialize msg_dict and send it to all connected clients except exclude."""
        data = (json.dumps(msg_dict) + "\n").encode("utf-8")
        dead = []
        with self._clients_lock:
            clients_snapshot = list(self._clients)
        for conn in clients_snapshot:
            if conn is exclude:
                continue
            try:
                conn.sendall(data)
            except OSError:
                dead.append(conn)
                logger.debug("Client disconnected during broadcast, removing")
        if dead:
            with self._clients_lock:
                for conn in dead:
                    if conn in self._clients:
                        self._clients.remove(conn)

    def _send_to(self, conn: socket.socket, msg_dict: dict) -> None:
        """Send a single message directly to one client."""
        try:
            data = (json.dumps(msg_dict) + "\n").encode("utf-8")
            conn.sendall(data)
        except OSError as e:
            logger.debug("Could not send message to client: %s", e)

    def _handle_script_control(self, msg: dict, requester: socket.socket) -> None:
        """Handle a script_control command (runs in its own thread)."""
        action = msg.get("action")

        if not self._script_runner:
            self._send_to(requester, {"type": "script_error", "message": "Scripting is not configured"})
            return

        try:
            if action == "list":
                scripts = self._script_runner.registry.list()
                self._send_to(requester, {"type": "script_list", "scripts": scripts})

            elif action == "run":
                name = msg["name"]
                params = msg.get("params", {})
                self._script_runner.run(name, params)
                # script_status "running" is broadcast by the runner itself

            elif action == "cancel":
                run_id = msg["run_id"]
                ok = self._script_runner.cancel(run_id)
                self._send_to(requester, {"type": "script_cancel_ack", "run_id": run_id, "ok": ok})

            elif action == "upload":
                name = msg["name"]
                content = msg["content"]
                self._script_runner.registry.save(name, content)
                self._send_to(requester, {"type": "script_upload_ack", "name": name, "ok": True})

            elif action == "delete":
                name = msg["name"]
                self._script_runner.registry.delete(name)
                self._send_to(requester, {"type": "script_delete_ack", "name": name, "ok": True})

            elif action == "list_runs":
                runs = self._script_runner.list_runs()
                self._send_to(requester, {"type": "script_runs", "runs": runs})

            else:
                self._send_to(requester, {"type": "script_error", "message": f"Unknown action: {action}"})

        except KeyError as e:
            self._send_to(requester, {"type": "script_error", "message": f"Missing field: {e}"})
        except (FileNotFoundError, PermissionError, ValueError, SyntaxError) as e:
            self._send_to(requester, {"type": "script_error", "message": str(e)})
        except Exception as e:
            logger.error("script_control %s failed: %s", action, e)
            self._send_to(requester, {"type": "script_error", "message": str(e)})

    def _build_iproperty_from_command(self, msg: dict) -> IProperty:
        """Build an IProperty from a client 'new' command dict."""
        type_map = {
            "number": IndiPropertyType.NUMBER,
            "text": IndiPropertyType.TEXT,
            "switch": IndiPropertyType.SWITCH,
            "light": IndiPropertyType.LIGHT,
            "blob": IndiPropertyType.BLOB,
        }
        prop_type = type_map.get(msg.get("data_type", ""), IndiPropertyType.UNKNOWN)

        prop = IProperty(
            device_name=msg["device"],
            name=msg["property"],
            type=prop_type,
            perm=IndiPropertyPerm.RW,
        )

        for elem_dict in msg.get("elements", []):
            elem = IPropertyElement(
                name=elem_dict["name"],
                value=str(elem_dict.get("value", "")),
            )
            prop.elements[elem.name] = elem

        return prop
