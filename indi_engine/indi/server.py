import logging
import shutil
import subprocess
import time
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def detect_mode(service_name: str = "indiserver") -> str:
    """Return 'systemd' if indiserver is managed by systemd, else 'process'."""
    if shutil.which("systemctl") is None:
        return "process"
    result = subprocess.run(
        ["systemctl", "is-active", "--quiet", service_name],
        capture_output=True,
    )
    return "systemd" if result.returncode == 0 else "process"


# ---------------------------------------------------------------------------
# Process-based manager (default)
# ---------------------------------------------------------------------------

class ProcessServerManager:
    """Manage indiserver as a direct subprocess."""

    def __init__(
        self,
        drivers: list[str],
        port: int = 7624,
        verbose: bool = False,
        config_path: Path | None = None,
    ):
        self._drivers = list(drivers)
        self._port = port
        self._verbose = verbose
        self._config_path = config_path
        self._process: subprocess.Popen | None = None

    def start(self) -> None:
        if self.is_running():
            logger.warning("indiserver is already running (pid %d)", self._process.pid)
            return
        self._launch()

    def stop(self) -> None:
        if not self.is_running():
            logger.warning("indiserver is not running")
            return
        logger.info("Stopping indiserver (pid %d) …", self._process.pid)
        self._process.terminate()
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logger.warning("indiserver did not stop gracefully; killing it")
            self._process.kill()
            self._process.wait()
        self._process = None
        logger.info("indiserver stopped")

    def restart(self, drivers: list[str] | None = None) -> None:
        if drivers is not None:
            self._drivers = list(drivers)
        self.stop()
        time.sleep(1)
        self._launch()

    def add_driver(self, driver: str) -> None:
        if driver in self._drivers:
            logger.warning("Driver %s is already loaded", driver)
            return
        self._drivers.append(driver)
        self._save_drivers()
        logger.info("Added driver %s; restarting indiserver …", driver)
        self.restart()

    def remove_driver(self, driver: str) -> None:
        if driver not in self._drivers:
            logger.warning("Driver %s is not loaded", driver)
            return
        self._drivers.remove(driver)
        self._save_drivers()
        logger.info("Removed driver %s; restarting indiserver …", driver)
        self.restart()

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    @property
    def drivers(self) -> list[str]:
        return list(self._drivers)

    def _save_drivers(self) -> None:
        if self._config_path is None:
            return
        with open(self._config_path) as f:
            cfg = yaml.safe_load(f)
        cfg.setdefault("server", {})["drivers"] = list(self._drivers)
        with open(self._config_path, "w") as f:
            yaml.dump(cfg, f, default_flow_style=False, sort_keys=False)
        logger.debug("Saved driver list to %s", self._config_path)

    def _launch(self) -> None:
        indiserver = shutil.which("indiserver")
        if indiserver is None:
            raise FileNotFoundError(
                "indiserver not found on PATH. Is INDI installed?"
            )
        cmd = [indiserver, "-p", str(self._port)]
        if self._verbose:
            cmd.append("-v")
        cmd.extend(self._drivers)
        logger.info("Starting indiserver: %s", " ".join(cmd))
        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        logger.info("indiserver started (pid %d)", self._process.pid)


# ---------------------------------------------------------------------------
# Systemd-based manager
# ---------------------------------------------------------------------------

class SystemdServerManager:
    """Manage indiserver via systemctl (Linux only).

    The systemd unit is expected to read its driver list from the YAML config
    (e.g. via an ExecStart wrapper script). After add_driver / remove_driver
    the YAML is updated and the service is restarted so it picks up the change.
    """

    def __init__(
        self,
        service_name: str = "indiserver",
        drivers: list[str] | None = None,
        config_path: Path | None = None,
    ):
        self._service = service_name
        self._drivers = list(drivers or [])
        self._config_path = config_path

    def start(self) -> None:
        logger.info("Starting systemd service %s …", self._service)
        self._systemctl("start")

    def stop(self) -> None:
        logger.info("Stopping systemd service %s …", self._service)
        self._systemctl("stop")

    def restart(self, drivers: list[str] | None = None) -> None:
        if drivers is not None:
            self._drivers = list(drivers)
        logger.info("Restarting systemd service %s …", self._service)
        self._systemctl("restart")

    def add_driver(self, driver: str) -> None:
        if driver in self._drivers:
            logger.warning("Driver %s is already loaded", driver)
            return
        self._drivers.append(driver)
        self._save_drivers()
        logger.info("Added driver %s; restarting %s …", driver, self._service)
        self._systemctl("restart")

    def remove_driver(self, driver: str) -> None:
        if driver not in self._drivers:
            logger.warning("Driver %s is not loaded", driver)
            return
        self._drivers.remove(driver)
        self._save_drivers()
        logger.info("Removed driver %s; restarting %s …", driver, self._service)
        self._systemctl("restart")

    def is_running(self) -> bool:
        result = subprocess.run(
            ["systemctl", "is-active", "--quiet", self._service],
            capture_output=True,
        )
        return result.returncode == 0

    @property
    def drivers(self) -> list[str]:
        return list(self._drivers)

    def _systemctl(self, action: str) -> None:
        result = subprocess.run(
            ["systemctl", action, self._service],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"systemctl {action} {self._service} failed: {result.stderr.strip()}"
            )

    def _save_drivers(self) -> None:
        if self._config_path is None:
            return
        with open(self._config_path) as f:
            cfg = yaml.safe_load(f)
        cfg.setdefault("server", {})["drivers"] = list(self._drivers)
        with open(self._config_path, "w") as f:
            yaml.dump(cfg, f, default_flow_style=False, sort_keys=False)
        logger.debug("Saved driver list to %s", self._config_path)


# ---------------------------------------------------------------------------
# Backward-compatible alias
# ---------------------------------------------------------------------------

IndiServerManager = ProcessServerManager
