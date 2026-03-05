"""
Tests for IndiClient.

PyIndi is a C extension that requires libindi installed on the host, so we
mock the entire module before importing IndiClient.
"""
import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from indi_engine.indi.protocol.constants import IndiPropertyType


# ---------------------------------------------------------------------------
# Build a minimal PyIndi stub so IndiClient can be imported without libindi.
# ---------------------------------------------------------------------------

def _make_pyindi_stub():
    stub = ModuleType("PyIndi")

    class BaseClient:
        def __init__(self):
            pass

        def setServer(self, host, port):
            self._host = host
            self._port = port

        def getHost(self):
            return self._host

        def getPort(self):
            return self._port

    stub.BaseClient = BaseClient
    stub.INDI_NUMBER = "NUMBER"
    stub.INDI_TEXT = "TEXT"
    stub.INDI_SWITCH = "SWITCH"
    stub.INDI_LIGHT = "LIGHT"
    return stub


_pyindi_stub = _make_pyindi_stub()
sys.modules.setdefault("PyIndi", _pyindi_stub)

# Now it is safe to import IndiClient
from indi_engine.indi.client import IndiClient, _extract_value  # noqa: E402
from indi_engine.state.manager import DeviceStateManager  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_property(device="Telescope", name="RA", ptype=IndiPropertyType.NUMBER, values=None):
    p = MagicMock()
    p.getDeviceName.return_value = device
    p.getName.return_value = name
    p.getType.return_value = ptype

    if ptype == IndiPropertyType.NUMBER:
        items = [MagicMock(**{"getName.return_value": k, "getValue.return_value": v}) for k, v in (values or {}).items()]
        p.getNumber.return_value = items
    elif ptype == IndiPropertyType.TEXT:
        items = [MagicMock(**{"getName.return_value": k, "getText.return_value": v}) for k, v in (values or {}).items()]
        p.getText.return_value = items
    elif ptype == IndiPropertyType.SWITCH:
        items = [MagicMock(**{"getName.return_value": k, "getValue.return_value": v}) for k, v in (values or {}).items()]
        p.getSwitch.return_value = items
    elif ptype == IndiPropertyType.LIGHT:
        items = [MagicMock(**{"getName.return_value": k, "getValue.return_value": v}) for k, v in (values or {}).items()]
        p.getLight.return_value = items

    return p


# ---------------------------------------------------------------------------
# IndiClient constructor
# ---------------------------------------------------------------------------

def test_init_sets_server():
    client = IndiClient(host="myhost", port=9999)
    assert client.getHost() == "myhost"
    assert client.getPort() == 9999


def test_init_default_host_port():
    client = IndiClient()
    assert client.getHost() == "localhost"
    assert client.getPort() == 7624


# ---------------------------------------------------------------------------
# newProperty / updateProperty → state manager
# ---------------------------------------------------------------------------

def test_new_property_does_not_raise():
    # State manager updates are handled internally by PurePythonIndiClient
    # (tested in test_protocol_client.py). Here we verify the callback doesn't raise.
    mgr = DeviceStateManager()
    client = IndiClient(state_manager=mgr)
    p = _mock_property(device="Telescope", name="RA", ptype=IndiPropertyType.NUMBER, values={"RA": 12.5})
    client.newProperty(p)  # just logs, no exception


def test_update_property_does_not_raise():
    mgr = DeviceStateManager()
    client = IndiClient(state_manager=mgr)
    p = _mock_property(device="CCD", name="EXPOSURE", ptype=IndiPropertyType.NUMBER, values={"EXPOSURE": 60.0})
    client.updateProperty(p)  # just logs, no exception


def test_remove_property_does_not_raise():
    mgr = DeviceStateManager()
    client = IndiClient(state_manager=mgr)
    p = _mock_property(device="Telescope", name="DEC", ptype=IndiPropertyType.NUMBER, values={"DEC": 45.0})
    client.removeProperty(p)  # just logs, no exception


def test_no_state_manager_does_not_raise():
    client = IndiClient()
    p = _mock_property()
    client.newProperty(p)
    client.updateProperty(p)
    client.removeProperty(p)


# ---------------------------------------------------------------------------
# _extract_value
# ---------------------------------------------------------------------------

def test_extract_number():
    p = _mock_property(ptype=IndiPropertyType.NUMBER, values={"RA": 12.5, "DEC": 45.0})
    result = _extract_value(p)
    assert result == {"RA": 12.5, "DEC": 45.0}


def test_extract_text():
    p = _mock_property(ptype=IndiPropertyType.TEXT, values={"LABEL": "hello"})
    result = _extract_value(p)
    assert result == {"LABEL": "hello"}


def test_extract_switch():
    p = _mock_property(ptype=IndiPropertyType.SWITCH, values={"ON": 1})
    result = _extract_value(p)
    assert result == {"ON": 1}


def test_extract_light():
    p = _mock_property(ptype=IndiPropertyType.LIGHT, values={"STATUS": 2})
    result = _extract_value(p)
    assert result == {"STATUS": 2}


def test_extract_unknown_type_returns_none():
    p = MagicMock()
    p.getType.return_value = IndiPropertyType.BLOB
    result = _extract_value(p)
    assert result is None


def test_extract_exception_returns_none():
    p = MagicMock()
    p.getType.return_value = IndiPropertyType.NUMBER
    p.getNumber.side_effect = RuntimeError("boom")
    result = _extract_value(p)
    assert result is None
