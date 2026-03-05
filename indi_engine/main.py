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
from indi_engine.state.manager import DeviceStateManager

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

    logger.info("Connecting to INDI server at %s:%d …", indi_host, indi_port)
    if not client.connectServer():
        logger.error("Could not connect to INDI server. Is indiserver running?")
        return

    # Watch all devices
    client.watchDevice("")

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

    client.disconnectServer()
    logger.info("Disconnected.")

    if server_manager:
        server_manager.stop()


if __name__ == "__main__":
    main()
