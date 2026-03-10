"""Bonjour/mDNS discovery for INDIEngine peers.

Each engine registers itself as a _indiengine._tcp.local. service and browses
for other engines on the local network. When engines appear or disappear,
engine_online / engine_offline messages are broadcast to all subscribed clients.
"""

import logging
import socket
from typing import Optional

from zeroconf import ServiceBrowser, ServiceInfo, Zeroconf

logger = logging.getLogger(__name__)

_SERVICE_TYPE = "_indiengine._tcp.local."


class EngineDiscovery:
    """Handles mDNS registration and peer discovery.

    Args:
        engine_identity: The local engine's EngineIdentity instance.
        port: The TCP port this engine's socket server listens on.
        socket_server: Used to broadcast engine_online/engine_offline events.
        capabilities: List of capability strings to include in TXT records.
    """

    def __init__(self, engine_identity, port: int, socket_server, capabilities: list = None):
        self._identity = engine_identity
        self._port = port
        self._socket_server = socket_server
        self._capabilities = capabilities or []
        self._zeroconf: Optional[Zeroconf] = None
        self._browser = None
        self.known_engines: dict = {}  # engine_id → {name, host, port, capabilities}

    def start(self) -> None:
        self._zeroconf = Zeroconf()
        info = self._build_service_info()
        self._zeroconf.register_service(info)
        self._browser = ServiceBrowser(self._zeroconf, _SERVICE_TYPE, handlers=[self._on_service_state_change])
        logger.info("Engine discovery started (id=%s, name=%s)", self._identity.id, self._identity.name)

    def stop(self) -> None:
        if self._zeroconf:
            try:
                self._zeroconf.unregister_service(self._build_service_info())
                self._zeroconf.close()
            except Exception as e:
                logger.debug("Discovery stop error: %s", e)
            self._zeroconf = None
        logger.info("Engine discovery stopped")

    def _build_service_info(self) -> ServiceInfo:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        service_name = f"{self._identity.id}.{_SERVICE_TYPE}"
        return ServiceInfo(
            type_=_SERVICE_TYPE,
            name=service_name,
            addresses=[socket.inet_aton(local_ip)],
            port=self._port,
            properties={
                b"engine_id": self._identity.id.encode(),
                b"name": self._identity.name.encode(),
                b"capabilities": ",".join(self._capabilities).encode(),
            },
        )

    def _on_service_state_change(self, zeroconf: Zeroconf, service_type: str, name: str, state_change) -> None:
        from zeroconf import ServiceStateChange

        if state_change == ServiceStateChange.Added:
            info = zeroconf.get_service_info(service_type, name)
            if info is None:
                return
            props = {k.decode(): v.decode() for k, v in info.properties.items()}
            engine_id = props.get("engine_id", "")
            if engine_id == self._identity.id:
                return  # ignore self

            engine_name = props.get("name", name)
            host = socket.inet_ntoa(info.addresses[0]) if info.addresses else ""
            caps = [c for c in props.get("capabilities", "").split(",") if c]
            self.known_engines[engine_id] = {
                "name": engine_name,
                "host": host,
                "port": info.port,
                "capabilities": caps,
            }
            logger.info("Peer engine online: %s (%s:%d)", engine_name, host, info.port)
            self._socket_server.broadcast({
                "type": "engine_online",
                "engine_id": engine_id,
                "name": engine_name,
                "host": host,
                "port": info.port,
                "capabilities": caps,
            })

        elif state_change == ServiceStateChange.Removed:
            info = zeroconf.get_service_info(service_type, name)
            props = {}
            if info:
                props = {k.decode(): v.decode() for k, v in info.properties.items()}
            engine_id = props.get("engine_id", name)
            if engine_id == self._identity.id:
                return

            entry = self.known_engines.pop(engine_id, {})
            engine_name = entry.get("name", engine_id)
            logger.info("Peer engine offline: %s", engine_name)
            self._socket_server.broadcast({
                "type": "engine_offline",
                "engine_id": engine_id,
                "name": engine_name,
            })
