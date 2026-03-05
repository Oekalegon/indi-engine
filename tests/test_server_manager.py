import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from indi_engine.indi.server import ProcessServerManager


def _make_manager(drivers=None, config_path=None):
    return ProcessServerManager(
        drivers=drivers or ["indi_simulator_telescope"],
        port=7624,
        config_path=config_path,
    )


def _running_process():
    proc = MagicMock()
    proc.pid = 1234
    proc.poll.return_value = None  # process is alive
    return proc


def _stopped_process():
    proc = MagicMock()
    proc.pid = 1234
    proc.poll.return_value = 0  # process has exited
    return proc


# --- is_running ---

def test_is_running_false_when_no_process():
    mgr = _make_manager()
    assert not mgr.is_running()


def test_is_running_true_when_process_alive():
    mgr = _make_manager()
    mgr._process = _running_process()
    assert mgr.is_running()


def test_is_running_false_when_process_exited():
    mgr = _make_manager()
    mgr._process = _stopped_process()
    assert not mgr.is_running()


# --- start ---

@patch("indi_engine.indi.server.shutil.which", return_value="/usr/bin/indiserver")
@patch("indi_engine.indi.server.subprocess.Popen")
def test_start_launches_process(mock_popen, mock_which):
    mock_popen.return_value = _running_process()
    mgr = _make_manager()
    mgr.start()
    mock_popen.assert_called_once()
    cmd = mock_popen.call_args[0][0]
    assert "indiserver" in cmd[0]
    assert "indi_simulator_telescope" in cmd


@patch("indi_engine.indi.server.shutil.which", return_value="/usr/bin/indiserver")
@patch("indi_engine.indi.server.subprocess.Popen")
def test_start_when_already_running_does_not_relaunch(mock_popen, mock_which):
    mgr = _make_manager()
    mgr._process = _running_process()
    mgr.start()
    mock_popen.assert_not_called()


@patch("indi_engine.indi.server.shutil.which", return_value=None)
def test_start_raises_when_indiserver_not_found(mock_which):
    mgr = _make_manager()
    with pytest.raises(FileNotFoundError):
        mgr.start()


@patch("indi_engine.indi.server.shutil.which", return_value="/usr/bin/indiserver")
@patch("indi_engine.indi.server.subprocess.Popen")
def test_start_includes_port(mock_popen, mock_which):
    mock_popen.return_value = _running_process()
    mgr = ProcessServerManager(drivers=["indi_simulator_telescope"], port=9999)
    mgr.start()
    cmd = mock_popen.call_args[0][0]
    assert "-p" in cmd
    assert "9999" in cmd


@patch("indi_engine.indi.server.shutil.which", return_value="/usr/bin/indiserver")
@patch("indi_engine.indi.server.subprocess.Popen")
def test_start_verbose_flag(mock_popen, mock_which):
    mock_popen.return_value = _running_process()
    mgr = ProcessServerManager(drivers=[], port=7624, verbose=True)
    mgr.start()
    cmd = mock_popen.call_args[0][0]
    assert "-v" in cmd


# --- stop ---

def test_stop_terminates_process():
    mgr = _make_manager()
    proc = _running_process()
    mgr._process = proc
    mgr.stop()
    proc.terminate.assert_called_once()
    assert mgr._process is None


def test_stop_kills_if_terminate_times_out():
    mgr = _make_manager()
    proc = _running_process()
    proc.wait.side_effect = [subprocess.TimeoutExpired(cmd="indiserver", timeout=5), None]
    mgr._process = proc
    mgr.stop()
    proc.kill.assert_called_once()


def test_stop_when_not_running_does_nothing():
    mgr = _make_manager()
    mgr.stop()  # should not raise


# --- add_driver / remove_driver ---

@patch("indi_engine.indi.server.time.sleep")
@patch("indi_engine.indi.server.shutil.which", return_value="/usr/bin/indiserver")
@patch("indi_engine.indi.server.subprocess.Popen")
def test_add_driver(mock_popen, mock_which, mock_sleep):
    mock_popen.return_value = _running_process()
    mgr = _make_manager(drivers=["indi_simulator_telescope"])
    mgr._process = _running_process()
    mgr.add_driver("indi_simulator_ccd")
    assert "indi_simulator_ccd" in mgr.drivers


@patch("indi_engine.indi.server.time.sleep")
@patch("indi_engine.indi.server.shutil.which", return_value="/usr/bin/indiserver")
@patch("indi_engine.indi.server.subprocess.Popen")
def test_add_duplicate_driver_does_not_duplicate(mock_popen, mock_which, mock_sleep):
    mock_popen.return_value = _running_process()
    mgr = _make_manager(drivers=["indi_simulator_telescope"])
    mgr.add_driver("indi_simulator_telescope")
    assert mgr.drivers.count("indi_simulator_telescope") == 1
    mock_popen.assert_not_called()


@patch("indi_engine.indi.server.time.sleep")
@patch("indi_engine.indi.server.shutil.which", return_value="/usr/bin/indiserver")
@patch("indi_engine.indi.server.subprocess.Popen")
def test_remove_driver(mock_popen, mock_which, mock_sleep):
    mock_popen.return_value = _running_process()
    mgr = _make_manager(drivers=["indi_simulator_telescope", "indi_simulator_ccd"])
    mgr._process = _running_process()
    mgr.remove_driver("indi_simulator_ccd")
    assert "indi_simulator_ccd" not in mgr.drivers


@patch("indi_engine.indi.server.time.sleep")
@patch("indi_engine.indi.server.shutil.which", return_value="/usr/bin/indiserver")
@patch("indi_engine.indi.server.subprocess.Popen")
def test_remove_nonexistent_driver_does_not_restart(mock_popen, mock_which, mock_sleep):
    mock_popen.return_value = _running_process()
    mgr = _make_manager(drivers=["indi_simulator_telescope"])
    mgr.remove_driver("ghost_driver")
    mock_popen.assert_not_called()


# --- drivers property ---

def test_drivers_returns_copy():
    mgr = _make_manager(["indi_simulator_telescope"])
    drivers = mgr.drivers
    drivers.append("hacked")
    assert "hacked" not in mgr.drivers


# --- YAML persistence ---

def _write_config(path: Path, drivers: list[str]) -> None:
    path.write_text(
        yaml.dump(
            {"indi": {"host": "localhost", "port": 7624}, "server": {"drivers": drivers}},
            default_flow_style=False,
            sort_keys=False,
        )
    )


@patch("indi_engine.indi.server.time.sleep")
@patch("indi_engine.indi.server.shutil.which", return_value="/usr/bin/indiserver")
@patch("indi_engine.indi.server.subprocess.Popen")
def test_add_driver_persists_to_yaml(mock_popen, mock_which, mock_sleep, tmp_path):
    cfg_file = tmp_path / "main.yaml"
    _write_config(cfg_file, ["indi_simulator_telescope"])
    mock_popen.return_value = _running_process()

    mgr = _make_manager(drivers=["indi_simulator_telescope"], config_path=cfg_file)
    mgr._process = _running_process()
    mgr.add_driver("indi_simulator_ccd")

    saved = yaml.safe_load(cfg_file.read_text())
    assert "indi_simulator_ccd" in saved["server"]["drivers"]


@patch("indi_engine.indi.server.time.sleep")
@patch("indi_engine.indi.server.shutil.which", return_value="/usr/bin/indiserver")
@patch("indi_engine.indi.server.subprocess.Popen")
def test_remove_driver_persists_to_yaml(mock_popen, mock_which, mock_sleep, tmp_path):
    cfg_file = tmp_path / "main.yaml"
    _write_config(cfg_file, ["indi_simulator_telescope", "indi_simulator_ccd"])
    mock_popen.return_value = _running_process()

    mgr = _make_manager(
        drivers=["indi_simulator_telescope", "indi_simulator_ccd"], config_path=cfg_file
    )
    mgr._process = _running_process()
    mgr.remove_driver("indi_simulator_ccd")

    saved = yaml.safe_load(cfg_file.read_text())
    assert "indi_simulator_ccd" not in saved["server"]["drivers"]


def test_save_drivers_skipped_when_no_config_path():
    mgr = _make_manager(["indi_simulator_telescope"], config_path=None)
    mgr._save_drivers()  # should not raise
