import logging
import signal
import time

from indi_engine import config
from indi_engine.indi.client import IndiClient
from indi_engine.indi.server import (
    ProcessServerManager,
    SystemdServerManager,
    detect_mode,
)
from indi_engine.server.socket_server import SocketServer
from indi_engine.server.serializer import serialize_property, serialize_message
from indi_engine.state.manager import DeviceStateManager
from indi_engine.scripting.api import PropertyUpdateBus
from indi_engine.scripting.registry import ScriptRegistry
from indi_engine.scripting.runner import ScriptRunner

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    config_path = config.DEFAULT_CONFIG_PATH
    cfg = config.load(config_path)
    indi_host = cfg["indi"]["host"]
    indi_port = cfg["indi"]["port"]
    server_cfg = cfg.get("server", {})

    server_manager = None
    if server_cfg.get("manage", False):
        mode = server_cfg.get("mode", "process")
        if mode == "auto":
            service_name = server_cfg.get("service_name", "indiserver")
            mode = detect_mode(service_name)
            logger.info("Auto-detected server mode: %s", mode)

        if mode == "systemd":
            server_manager = SystemdServerManager(
                service_name=server_cfg.get("service_name", "indiserver"),
                drivers=server_cfg.get("drivers", []),
                config_path=config_path,
            )
        else:
            server_manager = ProcessServerManager(
                drivers=server_cfg.get("drivers", []),
                port=indi_port,
                verbose=server_cfg.get("verbose", False),
                config_path=config_path,
            )

        logger.info("Using %s server manager", mode)
        server_manager.start()

    state_manager = DeviceStateManager()
    client = IndiClient(host=indi_host, port=indi_port, state_manager=state_manager)

    # Start the engine socket server and wire INDI callbacks to broadcast
    engine_cfg = cfg.get("engine", {})
    socket_server = SocketServer(
        host=engine_cfg.get("host", "0.0.0.0"),
        port=engine_cfg.get("port", 8624),
    )
    socket_server.set_indi_client(client)
    socket_server.set_server_manager(server_manager)
    socket_server.start()

    _orig_newProperty         = client.newProperty
    _orig_updateProperty      = client.updateProperty
    _orig_newMessage          = client.newMessage
    _orig_newUniversalMessage = client.newUniversalMessage

    def _on_new_property(prop):
        _orig_newProperty(prop)
        socket_server.broadcast(serialize_property(prop, "def"))

    def _on_update_property(prop):
        _orig_updateProperty(prop)
        socket_server.broadcast(serialize_property(prop, "set"))

    def _on_new_message(device, text):
        _orig_newMessage(device, text)
        socket_server.broadcast(serialize_message(device.getDeviceName(), text, timestamp=None))

    def _on_universal_message(text):
        _orig_newUniversalMessage(text)
        socket_server.broadcast(serialize_message(None, text, timestamp=None))

    client.newProperty         = _on_new_property
    client.updateProperty      = _on_update_property
    client.newMessage          = _on_new_message
    client.newUniversalMessage = _on_universal_message

    # Wire scripting engine
    scripting_cfg = cfg.get("scripting", {})
    update_bus = PropertyUpdateBus()

    _orig_update_property = client.updateProperty

    def _on_update_property_with_bus(prop):
        _orig_update_property(prop)
        update_bus.notify(prop)

    client.updateProperty = _on_update_property_with_bus

    registry = ScriptRegistry(
        builtin_dir=scripting_cfg.get("builtin_dir", "scripts/builtin"),
        user_dir=scripting_cfg.get("user_dir", "scripts/user"),
    )
    script_runner = ScriptRunner(
        registry=registry,
        indi_client=client,
        update_bus=update_bus,
        broadcast_fn=socket_server.broadcast,
        max_workers=scripting_cfg.get("max_workers", 4),
        default_timeout=scripting_cfg.get("default_timeout", 3600.0),
    )
    socket_server.set_script_runner(script_runner)
    logger.info("Scripting engine ready (%d workers)", scripting_cfg.get("max_workers", 4))

    def _connect_indi(max_attempts: int = 10) -> bool:
        for attempt in range(1, max_attempts + 1):
            try:
                client.connectServer()
                client.watchDevice("")
                return True
            except Exception as e:
                if attempt == max_attempts:
                    logger.error("Could not connect to INDI server after %d attempts: %s", max_attempts, e)
                    return False
                logger.info("INDI server not ready yet, retrying in 1 s … (%d/%d)", attempt, max_attempts)
                time.sleep(1)
        return False

    socket_server.set_reconnect_callback(_connect_indi)

    logger.info("Connecting to INDI server at %s:%d …", indi_host, indi_port)
    if not _connect_indi():
        socket_server.stop()
        return

    stop = False

    def _handle_signal(sig, frame):
        nonlocal stop
        logger.info("Shutting down …")
        stop = True

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    logger.info("Engine running. Press Ctrl+C to stop.")
    while not stop:
        time.sleep(1)

    script_runner.shutdown()
    socket_server.stop()
    client.disconnectServer()
    logger.info("Disconnected.")

    if server_manager:
        server_manager.stop()


if __name__ == "__main__":
    main()
