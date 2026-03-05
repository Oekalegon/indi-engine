import threading

from indi_engine.state.manager import DeviceStateManager


def test_update_and_get_device():
    mgr = DeviceStateManager()
    mgr.update("Telescope", "RA", 12.5)
    assert mgr.get_device("Telescope") == {"RA": 12.5}


def test_update_overwrites_existing_value():
    mgr = DeviceStateManager()
    mgr.update("Telescope", "RA", 12.5)
    mgr.update("Telescope", "RA", 15.0)
    assert mgr.get_device("Telescope")["RA"] == 15.0


def test_get_device_unknown_returns_empty():
    mgr = DeviceStateManager()
    assert mgr.get_device("Unknown") == {}


def test_remove_property():
    mgr = DeviceStateManager()
    mgr.update("CCD", "EXPOSURE", 30)
    mgr.remove("CCD", "EXPOSURE")
    assert "EXPOSURE" not in mgr.get_device("CCD")


def test_remove_nonexistent_property_does_not_raise():
    mgr = DeviceStateManager()
    mgr.remove("Ghost", "PROP")  # should not raise


def test_get_all_returns_all_devices():
    mgr = DeviceStateManager()
    mgr.update("Telescope", "RA", 1.0)
    mgr.update("CCD", "EXPOSURE", 30)
    state = mgr.get_all()
    assert "Telescope" in state
    assert "CCD" in state


def test_get_all_returns_copy():
    mgr = DeviceStateManager()
    mgr.update("Telescope", "RA", 1.0)
    state = mgr.get_all()
    state["Telescope"]["RA"] = 999
    assert mgr.get_device("Telescope")["RA"] == 1.0


def test_thread_safety():
    mgr = DeviceStateManager()
    errors = []

    def writer():
        try:
            for i in range(100):
                mgr.update("Dev", f"PROP_{i}", i)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=writer) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
