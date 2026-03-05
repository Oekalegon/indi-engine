import threading


class DeviceStateManager:
    """Thread-safe store of device property state received from INDI."""

    def __init__(self):
        self._lock = threading.Lock()
        # { device_name: { property_name: value } }
        self._state: dict[str, dict[str, object]] = {}

    def update(self, device: str, property_name: str, value) -> None:
        with self._lock:
            self._state.setdefault(device, {})[property_name] = value

    def remove(self, device: str, property_name: str) -> None:
        with self._lock:
            if device in self._state:
                self._state[device].pop(property_name, None)

    def get_device(self, device: str) -> dict:
        with self._lock:
            return dict(self._state.get(device, {}))

    def get_all(self) -> dict:
        with self._lock:
            return {d: dict(props) for d, props in self._state.items()}
