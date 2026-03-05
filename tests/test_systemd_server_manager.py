import subprocess
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
import yaml

from indi_engine.indi.server import SystemdServerManager, detect_mode


# ---------------------------------------------------------------------------
# detect_mode
# ---------------------------------------------------------------------------

@patch("indi_engine.indi.server.shutil.which", return_value=None)
def test_detect_mode_no_systemctl(mock_which):
    assert detect_mode() == "process"


@patch("indi_engine.indi.server.subprocess.run")
@patch("indi_engine.indi.server.shutil.which", return_value="/usr/bin/systemctl")
def test_detect_mode_service_active(mock_which, mock_run):
    mock_run.return_value = MagicMock(returncode=0)
    assert detect_mode("indiserver") == "systemd"
    mock_run.assert_called_once_with(
        ["systemctl", "is-active", "--quiet", "indiserver"],
        capture_output=True,
    )


@patch("indi_engine.indi.server.subprocess.run")
@patch("indi_engine.indi.server.shutil.which", return_value="/usr/bin/systemctl")
def test_detect_mode_service_inactive(mock_which, mock_run):
    mock_run.return_value = MagicMock(returncode=3)  # systemd exit code for inactive
    assert detect_mode("indiserver") == "process"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_manager(drivers=None, service_name="indiserver", config_path=None):
    return SystemdServerManager(
        service_name=service_name,
        drivers=drivers or ["indi_simulator_telescope"],
        config_path=config_path,
    )


def _ok():
    return MagicMock(returncode=0, stderr="")


def _fail(msg="error"):
    return MagicMock(returncode=1, stderr=msg)


# ---------------------------------------------------------------------------
# start / stop / restart
# ---------------------------------------------------------------------------

@patch("indi_engine.indi.server.subprocess.run")
def test_start_calls_systemctl(mock_run):
    mock_run.return_value = _ok()
    _make_manager().start()
    mock_run.assert_called_once_with(
        ["systemctl", "start", "indiserver"],
        capture_output=True, text=True,
    )


@patch("indi_engine.indi.server.subprocess.run")
def test_stop_calls_systemctl(mock_run):
    mock_run.return_value = _ok()
    _make_manager().stop()
    mock_run.assert_called_once_with(
        ["systemctl", "stop", "indiserver"],
        capture_output=True, text=True,
    )


@patch("indi_engine.indi.server.subprocess.run")
def test_restart_calls_systemctl(mock_run):
    mock_run.return_value = _ok()
    _make_manager().restart()
    mock_run.assert_called_once_with(
        ["systemctl", "restart", "indiserver"],
        capture_output=True, text=True,
    )


@patch("indi_engine.indi.server.subprocess.run")
def test_systemctl_failure_raises(mock_run):
    mock_run.return_value = _fail("Unit not found.")
    with pytest.raises(RuntimeError, match="Unit not found"):
        _make_manager().start()


# ---------------------------------------------------------------------------
# is_running
# ---------------------------------------------------------------------------

@patch("indi_engine.indi.server.subprocess.run")
def test_is_running_true_when_active(mock_run):
    mock_run.return_value = MagicMock(returncode=0)
    assert _make_manager().is_running() is True


@patch("indi_engine.indi.server.subprocess.run")
def test_is_running_false_when_inactive(mock_run):
    mock_run.return_value = MagicMock(returncode=3)
    assert _make_manager().is_running() is False


# ---------------------------------------------------------------------------
# add_driver / remove_driver
# ---------------------------------------------------------------------------

@patch("indi_engine.indi.server.subprocess.run")
def test_add_driver_updates_list_and_restarts(mock_run):
    mock_run.return_value = _ok()
    mgr = _make_manager(drivers=["indi_simulator_telescope"])
    mgr.add_driver("indi_simulator_ccd")
    assert "indi_simulator_ccd" in mgr.drivers
    mock_run.assert_called_with(
        ["systemctl", "restart", "indiserver"],
        capture_output=True, text=True,
    )


@patch("indi_engine.indi.server.subprocess.run")
def test_add_duplicate_driver_does_nothing(mock_run):
    mgr = _make_manager(drivers=["indi_simulator_telescope"])
    mgr.add_driver("indi_simulator_telescope")
    mock_run.assert_not_called()
    assert mgr.drivers.count("indi_simulator_telescope") == 1


@patch("indi_engine.indi.server.subprocess.run")
def test_remove_driver_updates_list_and_restarts(mock_run):
    mock_run.return_value = _ok()
    mgr = _make_manager(drivers=["indi_simulator_telescope", "indi_simulator_ccd"])
    mgr.remove_driver("indi_simulator_ccd")
    assert "indi_simulator_ccd" not in mgr.drivers
    mock_run.assert_called_with(
        ["systemctl", "restart", "indiserver"],
        capture_output=True, text=True,
    )


@patch("indi_engine.indi.server.subprocess.run")
def test_remove_nonexistent_driver_does_nothing(mock_run):
    mgr = _make_manager(drivers=["indi_simulator_telescope"])
    mgr.remove_driver("ghost_driver")
    mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# YAML persistence
# ---------------------------------------------------------------------------

def _write_config(path: Path, drivers: list[str]) -> None:
    path.write_text(
        yaml.dump(
            {"indi": {"host": "localhost", "port": 7624}, "server": {"drivers": drivers}},
            default_flow_style=False,
            sort_keys=False,
        )
    )


@patch("indi_engine.indi.server.subprocess.run")
def test_add_driver_persists_to_yaml(mock_run, tmp_path):
    mock_run.return_value = _ok()
    cfg_file = tmp_path / "main.yaml"
    _write_config(cfg_file, ["indi_simulator_telescope"])
    mgr = _make_manager(drivers=["indi_simulator_telescope"], config_path=cfg_file)
    mgr.add_driver("indi_simulator_ccd")
    saved = yaml.safe_load(cfg_file.read_text())
    assert "indi_simulator_ccd" in saved["server"]["drivers"]


@patch("indi_engine.indi.server.subprocess.run")
def test_remove_driver_persists_to_yaml(mock_run, tmp_path):
    mock_run.return_value = _ok()
    cfg_file = tmp_path / "main.yaml"
    _write_config(cfg_file, ["indi_simulator_telescope", "indi_simulator_ccd"])
    mgr = _make_manager(
        drivers=["indi_simulator_telescope", "indi_simulator_ccd"],
        config_path=cfg_file,
    )
    mgr.remove_driver("indi_simulator_ccd")
    saved = yaml.safe_load(cfg_file.read_text())
    assert "indi_simulator_ccd" not in saved["server"]["drivers"]
