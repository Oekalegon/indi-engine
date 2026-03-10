"""Tests for the scripting engine (sandbox, api, registry, runner).

No real INDI server is required — all INDI client interactions are mocked.
"""

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from indi_engine.scripting.api import (
    IndiScriptApi,
    PropertyUpdateBus,
    ScriptCancelledError,
    ScriptPausedError,
    TimeScriptApi,
)
from indi_engine.scripting.registry import ScriptRegistry
from indi_engine.scripting.runner import ScriptRunner
from indi_engine.scripting.sandbox import (
    ALLOWED_MODULES,
    check_syntax,
    compile_script,
    make_restricted_globals,
)
from indi_engine.indi.protocol.properties import IProperty, IPropertyElement
from indi_engine.indi.protocol.constants import IndiPropertyType, IndiPropertyState


# ---------------------------------------------------------------------------
# Sandbox tests
# ---------------------------------------------------------------------------


class TestSandboxBlockedImports:
    def test_blocks_import_os(self):
        code = compile_script("import os")
        g = make_restricted_globals({})
        with pytest.raises(ImportError):
            exec(code, g)

    def test_blocks_import_sys(self):
        code = compile_script("import sys")
        g = make_restricted_globals({})
        with pytest.raises(ImportError):
            exec(code, g)

    def test_blocks_import_subprocess(self):
        code = compile_script("import subprocess")
        g = make_restricted_globals({})
        with pytest.raises(ImportError):
            exec(code, g)

    def test_blocks_import_socket(self):
        code = compile_script("import socket")
        g = make_restricted_globals({})
        with pytest.raises(ImportError):
            exec(code, g)

    def test_allows_import_math(self):
        code = compile_script("import math\nresult = math.sqrt(4)")
        g = make_restricted_globals({})
        exec(code, g)
        assert g["result"] == 2.0

    def test_allowed_modules_set(self):
        assert "math" in ALLOWED_MODULES
        assert "astropy" in ALLOWED_MODULES
        assert "os" not in ALLOWED_MODULES
        assert "sys" not in ALLOWED_MODULES


class TestSandboxBlockedBuiltins:
    def test_blocks_open(self):
        code = compile_script("open('somefile')")
        g = make_restricted_globals({})
        with pytest.raises((NameError, AttributeError)):
            exec(code, g)

    def test_blocks_exec(self):
        # RestrictedPython blocks exec() calls at compile time
        with pytest.raises(SyntaxError):
            compile_script("exec('x=1')")

    def test_blocks_eval(self):
        # RestrictedPython blocks eval() calls at compile time
        with pytest.raises(SyntaxError):
            compile_script("eval('1+1')")


class TestSandboxAllowedBuiltins:
    def test_allows_len(self):
        code = compile_script("result = len([1, 2, 3])")
        g = make_restricted_globals({})
        exec(code, g)
        assert g["result"] == 3

    def test_allows_range(self):
        code = compile_script("result = list(range(3))")
        g = make_restricted_globals({})
        exec(code, g)
        assert g["result"] == [0, 1, 2]

    def test_allows_print(self):
        code = compile_script("print('hello')")
        g = make_restricted_globals({})
        exec(code, g)  # should not raise

    def test_allows_basic_arithmetic(self):
        code = compile_script("result = 2 ** 10")
        g = make_restricted_globals({})
        exec(code, g)
        assert g["result"] == 1024


class TestSandboxDunderBlocking:
    def test_blocks_class_subclasses_escape(self):
        # RestrictedPython blocks _-prefixed attribute access at compile time
        with pytest.raises(SyntaxError):
            compile_script("result = ().__class__.__bases__")


class TestCheckSyntax:
    def test_valid_source_passes(self):
        check_syntax("x = 1 + 1")

    def test_invalid_syntax_raises(self):
        with pytest.raises(SyntaxError):
            check_syntax("def (")


# ---------------------------------------------------------------------------
# PropertyUpdateBus tests
# ---------------------------------------------------------------------------


class TestPropertyUpdateBus:
    def test_subscriber_receives_notification(self):
        bus = PropertyUpdateBus()
        received = []
        prop = IProperty(device_name="Dev", name="PROP")

        unsub = bus.subscribe(lambda p: received.append(p))
        bus.notify(prop)

        assert len(received) == 1
        assert received[0] is prop
        unsub()

    def test_unsubscribe_stops_notifications(self):
        bus = PropertyUpdateBus()
        received = []
        prop = IProperty(device_name="Dev", name="PROP")

        unsub = bus.subscribe(lambda p: received.append(p))
        unsub()
        bus.notify(prop)

        assert received == []

    def test_multiple_subscribers(self):
        bus = PropertyUpdateBus()
        a, b = [], []
        prop = IProperty(device_name="Dev", name="PROP")

        u1 = bus.subscribe(lambda p: a.append(p))
        u2 = bus.subscribe(lambda p: b.append(p))
        bus.notify(prop)

        assert len(a) == 1
        assert len(b) == 1
        u1()
        u2()

    def test_failing_subscriber_does_not_prevent_others(self):
        bus = PropertyUpdateBus()
        received = []
        prop = IProperty(device_name="Dev", name="PROP")

        bus.subscribe(lambda p: (_ for _ in ()).throw(RuntimeError("oops")))
        bus.subscribe(lambda p: received.append(p))
        bus.notify(prop)

        assert len(received) == 1


# ---------------------------------------------------------------------------
# IndiScriptApi tests
# ---------------------------------------------------------------------------


def _make_mock_client():
    client = MagicMock()
    client._devices = {}
    return client


def _make_prop(device, name, state=IndiPropertyState.OK, elements=None, prop_type=IndiPropertyType.NUMBER):
    prop = IProperty(device_name=device, name=name, state=state, type=prop_type)
    if elements:
        for elem_name, val in elements.items():
            prop.elements[elem_name] = IPropertyElement(name=elem_name, value=str(val))
    return prop


class TestIndiScriptApiRead:
    def test_devices_returns_names(self):
        client = _make_mock_client()
        client._devices = {"Dev1": MagicMock(), "Dev2": MagicMock()}
        api = IndiScriptApi(client, PropertyUpdateBus(), threading.Event())
        assert sorted(api.devices()) == ["Dev1", "Dev2"]

    def test_get_property_returns_property(self):
        client = _make_mock_client()
        prop = _make_prop("Dev", "COORD")
        device = MagicMock()
        device.properties = {"COORD": prop}
        client._devices = {"Dev": device}

        api = IndiScriptApi(client, PropertyUpdateBus(), threading.Event())
        assert api.get_property("Dev", "COORD") is prop

    def test_get_property_returns_none_for_unknown_device(self):
        client = _make_mock_client()
        api = IndiScriptApi(client, PropertyUpdateBus(), threading.Event())
        assert api.get_property("Unknown", "PROP") is None

    def test_get_value_returns_float_for_number(self):
        client = _make_mock_client()
        prop = _make_prop("Dev", "COORD", elements={"RA": 10.5})
        device = MagicMock()
        device.properties = {"COORD": prop}
        client._devices = {"Dev": device}

        api = IndiScriptApi(client, PropertyUpdateBus(), threading.Event())
        assert api.get_value("Dev", "COORD", "RA") == 10.5

    def test_get_value_returns_none_for_missing_element(self):
        client = _make_mock_client()
        prop = _make_prop("Dev", "COORD", elements={"RA": 10.5})
        device = MagicMock()
        device.properties = {"COORD": prop}
        client._devices = {"Dev": device}

        api = IndiScriptApi(client, PropertyUpdateBus(), threading.Event())
        assert api.get_value("Dev", "COORD", "NONEXISTENT") is None


class TestIndiScriptApiWrite:
    def test_set_number_calls_send_new_number(self):
        client = _make_mock_client()
        api = IndiScriptApi(client, PropertyUpdateBus(), threading.Event())
        api.set_number("Dev", "COORD", {"RA": 10.5, "DEC": 45.0})
        client.sendNewNumber.assert_called_once()

    def test_set_text_calls_send_new_text(self):
        client = _make_mock_client()
        api = IndiScriptApi(client, PropertyUpdateBus(), threading.Event())
        api.set_text("Dev", "NAME", {"NAME_VALUE": "hello"})
        client.sendNewText.assert_called_once()

    def test_set_switch_calls_send_new_switch(self):
        client = _make_mock_client()
        api = IndiScriptApi(client, PropertyUpdateBus(), threading.Event())
        api.set_switch("Dev", "CONNECTION", {"CONNECT": "On"})
        client.sendNewSwitch.assert_called_once()

    def test_cancelled_event_raises_before_send(self):
        client = _make_mock_client()
        cancel = threading.Event()
        cancel.set()
        api = IndiScriptApi(client, PropertyUpdateBus(), cancel)
        with pytest.raises(ScriptCancelledError):
            api.set_number("Dev", "COORD", {"RA": 1.0})
        client.sendNewNumber.assert_not_called()


class TestWaitForState:
    def test_returns_true_if_already_in_state(self):
        client = _make_mock_client()
        prop = _make_prop("Dev", "PROP", state=IndiPropertyState.OK)
        device = MagicMock()
        device.properties = {"PROP": prop}
        client._devices = {"Dev": device}

        api = IndiScriptApi(client, PropertyUpdateBus(), threading.Event())
        assert api.wait_for_state("Dev", "PROP", "Ok", timeout=1.0) is True

    def test_returns_false_on_timeout(self):
        client = _make_mock_client()
        prop = _make_prop("Dev", "PROP", state=IndiPropertyState.BUSY)
        device = MagicMock()
        device.properties = {"PROP": prop}
        client._devices = {"Dev": device}

        api = IndiScriptApi(client, PropertyUpdateBus(), threading.Event())
        result = api.wait_for_state("Dev", "PROP", "Ok", timeout=0.3)
        assert result is False

    def test_returns_true_after_bus_notification(self):
        client = _make_mock_client()
        prop_busy = _make_prop("Dev", "PROP", state=IndiPropertyState.BUSY)
        device = MagicMock()
        device.properties = {"PROP": prop_busy}
        client._devices = {"Dev": device}

        bus = PropertyUpdateBus()
        api = IndiScriptApi(client, bus, threading.Event())

        prop_ok = _make_prop("Dev", "PROP", state=IndiPropertyState.OK)

        def notify_after_delay():
            time.sleep(0.1)
            bus.notify(prop_ok)

        threading.Thread(target=notify_after_delay, daemon=True).start()
        result = api.wait_for_state("Dev", "PROP", "Ok", timeout=2.0)
        assert result is True

    def test_raises_on_cancel(self):
        client = _make_mock_client()
        # Property doesn't exist → will wait
        client._devices = {}

        cancel = threading.Event()
        api = IndiScriptApi(client, PropertyUpdateBus(), cancel)

        def set_cancel():
            time.sleep(0.1)
            cancel.set()

        threading.Thread(target=set_cancel, daemon=True).start()
        with pytest.raises(ScriptCancelledError):
            api.wait_for_state("Dev", "PROP", "Ok", timeout=5.0)

    def test_raises_on_invalid_state(self):
        client = _make_mock_client()
        api = IndiScriptApi(client, PropertyUpdateBus(), threading.Event())
        with pytest.raises(ValueError):
            api.wait_for_state("Dev", "PROP", "InvalidState", timeout=0.1)


# ---------------------------------------------------------------------------
# TimeScriptApi tests
# ---------------------------------------------------------------------------


class TestTimeScriptApi:
    def test_sleep_completes_normally(self):
        api = TimeScriptApi(threading.Event())
        start = time.monotonic()
        api.sleep(0.05)
        assert time.monotonic() - start >= 0.04

    def test_sleep_raises_on_cancel(self):
        cancel = threading.Event()
        api = TimeScriptApi(cancel)

        def set_cancel():
            time.sleep(0.05)
            cancel.set()

        threading.Thread(target=set_cancel, daemon=True).start()
        with pytest.raises(ScriptCancelledError):
            api.sleep(5.0)


# ---------------------------------------------------------------------------
# ScriptRegistry tests
# ---------------------------------------------------------------------------


class TestScriptRegistry:
    def test_save_and_load_roundtrip(self, tmp_path):
        registry = ScriptRegistry(builtin_dir=str(tmp_path / "builtin"), user_dir=str(tmp_path / "user"))
        source = "result = 1 + 1"
        registry.save("my_script", source)
        assert registry.load("my_script") == source

    def test_load_raises_for_unknown(self, tmp_path):
        registry = ScriptRegistry(builtin_dir=str(tmp_path / "builtin"), user_dir=str(tmp_path / "user"))
        with pytest.raises(FileNotFoundError):
            registry.load("nonexistent")

    def test_save_rejects_syntax_error(self, tmp_path):
        registry = ScriptRegistry(builtin_dir=str(tmp_path / "builtin"), user_dir=str(tmp_path / "user"))
        with pytest.raises(SyntaxError):
            registry.save("bad", "def (")

    def test_save_rejects_path_traversal(self, tmp_path):
        registry = ScriptRegistry(builtin_dir=str(tmp_path / "builtin"), user_dir=str(tmp_path / "user"))
        with pytest.raises(ValueError):
            registry.save("../../etc/passwd", "x=1")

    def test_save_rejects_slash_in_name(self, tmp_path):
        registry = ScriptRegistry(builtin_dir=str(tmp_path / "builtin"), user_dir=str(tmp_path / "user"))
        with pytest.raises(ValueError):
            registry.save("foo/bar", "x=1")

    def test_delete_removes_user_script(self, tmp_path):
        registry = ScriptRegistry(builtin_dir=str(tmp_path / "builtin"), user_dir=str(tmp_path / "user"))
        registry.save("to_delete", "x=1")
        registry.delete("to_delete")
        with pytest.raises(FileNotFoundError):
            registry.load("to_delete")

    def test_delete_raises_for_builtin(self, tmp_path):
        builtin_dir = tmp_path / "builtin"
        builtin_dir.mkdir(parents=True)
        (builtin_dir / "my_builtin.py").write_text("x=1")
        registry = ScriptRegistry(builtin_dir=str(builtin_dir), user_dir=str(tmp_path / "user"))
        with pytest.raises(PermissionError):
            registry.delete("my_builtin")

    def test_list_includes_builtin_and_user(self, tmp_path):
        builtin_dir = tmp_path / "builtin"
        builtin_dir.mkdir(parents=True)
        (builtin_dir / "builtin_script.py").write_text('"A builtin."\nx=1')

        registry = ScriptRegistry(builtin_dir=str(builtin_dir), user_dir=str(tmp_path / "user"))
        registry.save("user_script", '"A user script."\nx=2')

        scripts = registry.list()
        names = [s["name"] for s in scripts]
        assert "builtin_script" in names
        assert "user_script" in names

    def test_list_extracts_docstring(self, tmp_path):
        registry = ScriptRegistry(builtin_dir=str(tmp_path / "builtin"), user_dir=str(tmp_path / "user"))
        registry.save("described", '"This is the description."\nx=1')
        scripts = registry.list()
        described = next(s for s in scripts if s["name"] == "described")
        assert described["description"] == "This is the description."

    def test_save_rejects_oversized_script(self, tmp_path):
        registry = ScriptRegistry(builtin_dir=str(tmp_path / "builtin"), user_dir=str(tmp_path / "user"))
        big_source = "x = 1  # " + "A" * (64 * 1024)
        with pytest.raises(ValueError):
            registry.save("big", big_source)

    def test_user_overrides_builtin(self, tmp_path):
        builtin_dir = tmp_path / "builtin"
        builtin_dir.mkdir(parents=True)
        (builtin_dir / "shared.py").write_text("x = 'builtin'")

        registry = ScriptRegistry(builtin_dir=str(builtin_dir), user_dir=str(tmp_path / "user"))
        registry.save("shared", "x = 'user'")

        assert registry.load("shared") == "x = 'user'"


# ---------------------------------------------------------------------------
# ScriptRunner tests
# ---------------------------------------------------------------------------


def _make_runner(tmp_path, broadcasts=None):
    registry = ScriptRegistry(
        builtin_dir=str(tmp_path / "builtin"),
        user_dir=str(tmp_path / "user"),
    )
    client = _make_mock_client()
    bus = PropertyUpdateBus()
    broadcast_fn = (lambda msg: broadcasts.append(msg)) if broadcasts is not None else (lambda msg: None)
    runner = ScriptRunner(
        registry=registry,
        indi_client=client,
        update_bus=bus,
        broadcast_fn=broadcast_fn,
        max_workers=2,
    )
    return runner, registry


class TestScriptRunner:
    def test_simple_script_finishes(self, tmp_path):
        broadcasts = []
        runner, registry = _make_runner(tmp_path, broadcasts)
        registry.save("simple", "result = 1 + 1")

        run_id = runner.run("simple")
        # Wait for completion
        time.sleep(0.5)

        statuses = [m["status"] for m in broadcasts if m.get("type") == "script_status"]
        assert "finished" in statuses

    def test_run_returns_run_id(self, tmp_path):
        runner, registry = _make_runner(tmp_path)
        registry.save("noop", "pass")
        run_id = runner.run("noop")
        assert isinstance(run_id, str) and len(run_id) == 32

    def test_script_error_broadcasts_error_status(self, tmp_path):
        broadcasts = []
        runner, registry = _make_runner(tmp_path, broadcasts)
        registry.save("failing", "raise ValueError('test error')")

        runner.run("failing")
        time.sleep(0.5)

        error_msgs = [m for m in broadcasts if m.get("status") == "error"]
        assert error_msgs
        assert "test error" in error_msgs[0]["message"]

    def test_cancel_during_sleep(self, tmp_path):
        broadcasts = []
        runner, registry = _make_runner(tmp_path, broadcasts)
        # Script uses time_utils.sleep which checks cancel_event
        registry.save("sleeper", "time_utils.sleep(60)")

        run_id = runner.run("sleeper")
        time.sleep(0.1)
        runner.cancel(run_id)
        time.sleep(0.5)

        statuses = [m["status"] for m in broadcasts if m.get("type") == "script_status"]
        assert "cancelled" in statuses

    def test_multiple_concurrent_scripts(self, tmp_path):
        broadcasts = []
        runner, registry = _make_runner(tmp_path, broadcasts)
        registry.save("s1", "time_utils.sleep(0.05)")
        registry.save("s2", "time_utils.sleep(0.05)")

        id1 = runner.run("s1")
        id2 = runner.run("s2")
        assert id1 != id2

        time.sleep(0.5)

        run_ids = {m["run_id"] for m in broadcasts if m.get("type") == "script_status" and m.get("status") == "finished"}
        assert id1 in run_ids
        assert id2 in run_ids

    def test_log_function_broadcasts_running_status(self, tmp_path):
        broadcasts = []
        runner, registry = _make_runner(tmp_path, broadcasts)
        registry.save("logger", "log('step 1', 0.5)")

        runner.run("logger")
        time.sleep(0.5)

        progress_msgs = [m for m in broadcasts if m.get("message") == "step 1"]
        assert progress_msgs
        assert progress_msgs[0]["progress"] == 0.5

    def test_params_accessible_in_script(self, tmp_path):
        broadcasts = []
        runner, registry = _make_runner(tmp_path, broadcasts)
        registry.save("paramtest", "log(str(params['x']))")

        runner.run("paramtest", params={"x": 42})
        time.sleep(0.5)

        msgs = [m for m in broadcasts if m.get("message") == "42"]
        assert msgs

    def test_sandbox_blocks_os_import_in_runner(self, tmp_path):
        broadcasts = []
        runner, registry = _make_runner(tmp_path, broadcasts)
        registry.save("bad_import", "import os")

        runner.run("bad_import")
        time.sleep(0.5)

        error_msgs = [m for m in broadcasts if m.get("status") == "error"]
        assert error_msgs


# ---------------------------------------------------------------------------
# Serializer integration test
# ---------------------------------------------------------------------------


class TestSerializeScriptStatus:
    def test_returns_correct_dict(self):
        from indi_engine.server.serializer import serialize_script_status

        result = serialize_script_status("abc123", "dark_frames", "running", "step 1", 0.5)
        assert result == {
            "type": "script_status",
            "run_id": "abc123",
            "name": "dark_frames",
            "status": "running",
            "message": "step 1",
            "progress": 0.5,
        }

    def test_defaults(self):
        from indi_engine.server.serializer import serialize_script_status

        result = serialize_script_status("id", "name", "finished")
        assert result["message"] == ""
        assert result["progress"] == 0.0

    def test_resume_command_included_when_provided(self):
        from indi_engine.server.serializer import serialize_script_status

        resume = {"type": "script_control", "action": "run", "name": "capture_frame", "params": {"count": 5}}
        result = serialize_script_status("id", "name", "paused", resume_command=resume)
        assert result["resume_command"] == resume

    def test_resume_command_absent_when_not_provided(self):
        from indi_engine.server.serializer import serialize_script_status

        result = serialize_script_status("id", "name", "finished")
        assert "resume_command" not in result


# ---------------------------------------------------------------------------
# ScriptPausedError tests
# ---------------------------------------------------------------------------


class TestScriptPausedError:
    def test_default_resume_params_is_none(self):
        err = ScriptPausedError()
        assert err.resume_params is None

    def test_resume_params_stored(self):
        params = {"count": 3, "exposure": 10.0}
        err = ScriptPausedError(params)
        assert err.resume_params == params

    def test_is_exception(self):
        assert isinstance(ScriptPausedError(), Exception)


# ---------------------------------------------------------------------------
# IndiScriptApi checkpoint / pause tests
# ---------------------------------------------------------------------------


class TestCheckpoint:
    def test_checkpoint_stores_last_checkpoint(self):
        client = _make_mock_client()
        api = IndiScriptApi(client, PropertyUpdateBus(), threading.Event())
        params = {"count": 5, "exposure": 10.0}
        api.checkpoint(params)
        assert api._last_checkpoint == params

    def test_checkpoint_raises_paused_when_deferred_event_set(self):
        client = _make_mock_client()
        pause_deferred = threading.Event()
        pause_deferred.set()
        api = IndiScriptApi(client, PropertyUpdateBus(), threading.Event(),
                            pause_deferred=pause_deferred)
        with pytest.raises(ScriptPausedError) as exc_info:
            api.checkpoint({"count": 2})
        assert exc_info.value.resume_params == {"count": 2}

    def test_checkpoint_raises_paused_when_immediate_event_set(self):
        client = _make_mock_client()
        pause_immediate = threading.Event()
        pause_immediate.set()
        api = IndiScriptApi(client, PropertyUpdateBus(), threading.Event(),
                            pause_immediate=pause_immediate)
        with pytest.raises(ScriptPausedError):
            api.checkpoint({"count": 1})

    def test_checkpoint_raises_cancelled_before_pause(self):
        client = _make_mock_client()
        cancel = threading.Event()
        cancel.set()
        pause_deferred = threading.Event()
        pause_deferred.set()
        api = IndiScriptApi(client, PropertyUpdateBus(), cancel,
                            pause_deferred=pause_deferred)
        # cancel takes priority over pause
        with pytest.raises(ScriptCancelledError):
            api.checkpoint({"count": 1})

    def test_checkpoint_no_raise_when_no_pause(self):
        client = _make_mock_client()
        api = IndiScriptApi(client, PropertyUpdateBus(), threading.Event())
        # Should not raise
        api.checkpoint({"count": 5})


class TestPauseImmediateInterruptsWaitForState:
    def test_pause_immediate_raises_paused_error(self):
        client = _make_mock_client()
        # Property doesn't exist → will wait
        client._devices = {}

        pause_immediate = threading.Event()
        api = IndiScriptApi(client, PropertyUpdateBus(), threading.Event(),
                            pause_immediate=pause_immediate)

        def set_pause():
            time.sleep(0.1)
            pause_immediate.set()

        threading.Thread(target=set_pause, daemon=True).start()
        with pytest.raises(ScriptPausedError):
            api.wait_for_state("Dev", "PROP", "Ok", timeout=5.0)

    def test_pause_immediate_carries_last_checkpoint(self):
        client = _make_mock_client()
        client._devices = {}

        pause_immediate = threading.Event()
        api = IndiScriptApi(client, PropertyUpdateBus(), threading.Event(),
                            pause_immediate=pause_immediate)
        # Set a checkpoint before waiting
        api._last_checkpoint = {"count": 3}

        def set_pause():
            time.sleep(0.1)
            pause_immediate.set()

        threading.Thread(target=set_pause, daemon=True).start()
        with pytest.raises(ScriptPausedError) as exc_info:
            api.wait_for_state("Dev", "PROP", "Ok", timeout=5.0)
        assert exc_info.value.resume_params == {"count": 3}


class TestPauseImmediateInterruptsSleep:
    def test_sleep_raises_paused_on_immediate_pause(self):
        cancel = threading.Event()
        pause_immediate = threading.Event()
        checkpoint = {"count": 7}
        api = TimeScriptApi(cancel, pause_immediate=pause_immediate,
                            get_checkpoint=lambda: checkpoint)

        def set_pause():
            time.sleep(0.05)
            pause_immediate.set()

        threading.Thread(target=set_pause, daemon=True).start()
        with pytest.raises(ScriptPausedError) as exc_info:
            api.sleep(5.0)
        assert exc_info.value.resume_params == {"count": 7}


class TestUpdateBlobParams:
    def test_update_blob_params_calls_blob_register(self):
        client = _make_mock_client()
        registered = []
        api = IndiScriptApi(client, PropertyUpdateBus(), threading.Event(),
                            run_id="run123",
                            blob_register=lambda d, r, p: registered.append((d, r, p)))
        api.update_blob_params("CCD Simulator", {"frame_index": 2, "count": 5})
        assert registered == [("CCD Simulator", "run123", {"frame_index": 2, "count": 5})]

    def test_update_blob_params_no_op_without_run_id(self):
        client = _make_mock_client()
        registered = []
        api = IndiScriptApi(client, PropertyUpdateBus(), threading.Event(),
                            run_id=None,
                            blob_register=lambda d, r, p: registered.append((d, r, p)))
        api.update_blob_params("CCD Simulator", {"frame_index": 1})
        assert registered == []

    def test_update_blob_params_raises_if_cancelled(self):
        client = _make_mock_client()
        cancel = threading.Event()
        cancel.set()
        api = IndiScriptApi(client, PropertyUpdateBus(), cancel, run_id="run1",
                            blob_register=lambda d, r, p: None)
        with pytest.raises(ScriptCancelledError):
            api.update_blob_params("CCD Simulator", {"frame_index": 1})


# ---------------------------------------------------------------------------
# ScriptRunner pause tests
# ---------------------------------------------------------------------------


class TestScriptRunnerPause:
    def test_pause_deferred_broadcasts_paused_status(self, tmp_path):
        broadcasts = []
        runner, registry = _make_runner(tmp_path, broadcasts)
        # Script loops with checkpoints
        registry.save("looper", "\n".join([
            "for i in range(10):",
            "    indi.checkpoint({'count': 10 - i})",
            "    time_utils.sleep(0.5)",
        ]))

        run_id = runner.run("looper")
        time.sleep(0.15)
        runner.pause(run_id, finish_current=True)
        time.sleep(1.0)

        paused_msgs = [m for m in broadcasts if m.get("status") == "paused"]
        assert paused_msgs, "Expected a paused status message"
        assert paused_msgs[0]["run_id"] == run_id

    def test_pause_deferred_includes_resume_command(self, tmp_path):
        broadcasts = []
        runner, registry = _make_runner(tmp_path, broadcasts)
        # Script loops: checkpoint then short sleep, so pause_deferred fires at next checkpoint
        registry.save("checkpointer", "\n".join([
            "for i in range(20):",
            "    indi.checkpoint({'count': 20 - i, 'exposure': 10.0})",
            "    time_utils.sleep(0.2)",
        ]))

        run_id = runner.run("checkpointer")
        time.sleep(0.15)  # Let first iteration reach sleep
        runner.pause(run_id, finish_current=True)
        time.sleep(0.6)  # Wait for sleep to finish and checkpoint to fire

        paused_msgs = [m for m in broadcasts if m.get("status") == "paused"]
        assert paused_msgs, "Expected a paused status message"
        rc = paused_msgs[0].get("resume_command")
        assert rc is not None
        assert rc["type"] == "script_control"
        assert rc["action"] == "run"
        assert "count" in rc["params"]

    def test_pause_immediate_interrupts_sleep(self, tmp_path):
        broadcasts = []
        runner, registry = _make_runner(tmp_path, broadcasts)
        registry.save("long_sleep", "time_utils.sleep(60)")

        run_id = runner.run("long_sleep")
        time.sleep(0.1)
        runner.pause(run_id, finish_current=False)  # immediate
        time.sleep(0.5)

        paused_msgs = [m for m in broadcasts if m.get("status") == "paused"]
        assert paused_msgs

    def test_pause_returns_false_for_unknown_run(self, tmp_path):
        runner, _ = _make_runner(tmp_path)
        assert runner.pause("nonexistent-id") is False

    def test_pause_removes_run_from_active_runs(self, tmp_path):
        broadcasts = []
        runner, registry = _make_runner(tmp_path, broadcasts)
        registry.save("pausable", "indi.checkpoint({'count': 1})")

        run_id = runner.run("pausable")
        time.sleep(0.05)
        runner.pause(run_id, finish_current=True)
        time.sleep(0.5)

        # After pause, run should no longer be in active runs
        active = [r["run_id"] for r in runner.list_runs()]
        assert run_id not in active


# ---------------------------------------------------------------------------
# ScriptRunner blob registry tests
# ---------------------------------------------------------------------------


class TestBlobRegistry:
    def test_register_blob_device_stores_context(self, tmp_path):
        runner, _ = _make_runner(tmp_path)
        runner.register_blob_device("CCD Simulator", "run123", {"exposure": 10.0})
        ctx = runner.get_blob_context_for_device("CCD Simulator")
        assert ctx["run_id"] == "run123"
        assert ctx["capture_params"]["exposure"] == 10.0

    def test_blob_registry_cleared_on_run_complete(self, tmp_path):
        broadcasts = []
        runner, registry = _make_runner(tmp_path, broadcasts)
        # Script sleeps briefly so we can register blob device while it's still running
        registry.save("simple", "time_utils.sleep(0.2)")

        run_id = runner.run("simple")
        # Register while still running
        runner.register_blob_device("CCD Simulator", run_id, {"exposure": 5.0})
        # Verify it was registered
        assert runner.get_blob_context_for_device("CCD Simulator") is not None
        time.sleep(0.6)  # Let script finish

        ctx = runner.get_blob_context_for_device("CCD Simulator")
        assert ctx is None

    def test_register_blob_with_no_capture_params(self, tmp_path):
        runner, _ = _make_runner(tmp_path)
        runner.register_blob_device("CCD Simulator", "run42", None)
        ctx = runner.get_blob_context_for_device("CCD Simulator")
        assert ctx["capture_params"] == {}
