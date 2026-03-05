import pytest
from pathlib import Path

from indi_engine import config


def test_load_valid_config(tmp_path):
    cfg_file = tmp_path / "main.yaml"
    cfg_file.write_text("indi:\n  host: myhost\n  port: 1234\n")
    result = config.load(cfg_file)
    assert result["indi"]["host"] == "myhost"
    assert result["indi"]["port"] == 1234


def test_load_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        config.load(tmp_path / "nonexistent.yaml")


def test_load_full_config(tmp_path):
    cfg_file = tmp_path / "main.yaml"
    cfg_file.write_text(
        "indi:\n  host: localhost\n  port: 7624\n"
        "server:\n  manage: true\n  verbose: false\n  drivers:\n    - indi_simulator_telescope\n"
    )
    result = config.load(cfg_file)
    assert result["server"]["manage"] is True
    assert result["server"]["drivers"] == ["indi_simulator_telescope"]
