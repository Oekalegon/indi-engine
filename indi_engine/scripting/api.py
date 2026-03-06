"""Script-facing INDI API.

Provides the objects injected into every script execution context:
  - IndiScriptApi   (name: 'indi')       — INDI device access and commands
  - TimeScriptApi   (name: 'time_utils') — time utilities (astropy Time + sleep)
  - PropertyUpdateBus                    — fan-out hub used by wait_for_state/value

Also defines ScriptCancelledError, raised inside scripts when cancellation is requested.
"""

import time as _time
import threading
from typing import Callable, Optional

from indi_engine.indi.protocol.client import PurePythonIndiClient
from indi_engine.indi.protocol.properties import IProperty, IPropertyElement
from indi_engine.indi.protocol.constants import (
    IndiPropertyType,
    IndiPropertyPerm,
    IndiPropertyState,
)


class ScriptCancelledError(Exception):
    """Raised inside a script when cancellation is requested."""


class PropertyUpdateBus:
    """Thread-safe fan-out hub for updateProperty callbacks.

    One instance is shared across the engine. main.py hooks it into the INDI
    client's updateProperty callback chain. IndiScriptApi subscribes to it
    per wait_for_state / wait_for_value call.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: list[Callable[[IProperty], None]] = []

    def notify(self, prop: IProperty) -> None:
        """Called from the INDI reader thread when a property is updated."""
        with self._lock:
            subs = list(self._subscribers)
        for cb in subs:
            try:
                cb(prop)
            except Exception:
                pass

    def subscribe(self, cb: Callable[[IProperty], None]) -> Callable[[], None]:
        """Register a callback. Returns an unsubscribe callable."""
        with self._lock:
            self._subscribers.append(cb)

        def unsubscribe() -> None:
            with self._lock:
                try:
                    self._subscribers.remove(cb)
                except ValueError:
                    pass

        return unsubscribe


class IndiScriptApi:
    """Script-facing INDI API. Injected as 'indi' into script execution context.

    Scripts can read device state, send commands, and wait for state changes.
    All methods are proxied through PurePythonIndiClient — scripts never hold
    a direct reference to the client or any engine internals.
    """

    def __init__(
        self,
        indi_client: PurePythonIndiClient,
        update_bus: PropertyUpdateBus,
        cancel_event: threading.Event,
    ) -> None:
        self._client = indi_client
        self._bus = update_bus
        self._cancel = cancel_event

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def devices(self) -> list:
        """Return list of currently known device names."""
        return list(self._client._devices.keys())

    def get_property(self, device: str, name: str) -> Optional[IProperty]:
        """Return the IProperty object, or None if not known."""
        d = self._client._devices.get(device)
        return d.properties.get(name) if d else None

    def get_value(self, device: str, name: str, element: str):
        """Return the current element value, or None if not found.

        Number element values are returned as float; all others as str.
        """
        prop = self.get_property(device, name)
        if prop is None:
            return None
        elem = prop.elements.get(element)
        if elem is None:
            return None
        if prop.type == IndiPropertyType.NUMBER:
            try:
                return float(elem.value)
            except (ValueError, TypeError):
                return elem.value
        return elem.value

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def set_number(self, device: str, name: str, values: dict) -> None:
        """Send a newNumberVector command.

        Args:
            device: Device name.
            name: Property name.
            values: Dict mapping element name → float value.
        """
        self._require_not_cancelled()
        prop = self._build_prop(device, name, IndiPropertyType.NUMBER, values)
        self._client.sendNewNumber(prop)

    def set_text(self, device: str, name: str, values: dict) -> None:
        """Send a newTextVector command.

        Args:
            device: Device name.
            name: Property name.
            values: Dict mapping element name → str value.
        """
        self._require_not_cancelled()
        prop = self._build_prop(device, name, IndiPropertyType.TEXT, values)
        self._client.sendNewText(prop)

    def set_switch(self, device: str, name: str, values: dict) -> None:
        """Send a newSwitchVector command.

        Args:
            device: Device name.
            name: Property name.
            values: Dict mapping element name → "On" or "Off".
        """
        self._require_not_cancelled()
        prop = self._build_prop(device, name, IndiPropertyType.SWITCH, values)
        self._client.sendNewSwitch(prop)

    def connect_device(self, device: str) -> None:
        """Send a CONNECTION/CONNECT command to the device."""
        self._require_not_cancelled()
        self._client.connectDevice(device)

    def disconnect_device(self, device: str) -> None:
        """Send a CONNECTION/DISCONNECT command to the device."""
        self._require_not_cancelled()
        self._client.disconnectDevice(device)

    # ------------------------------------------------------------------
    # Blocking wait operations
    # ------------------------------------------------------------------

    def wait_for_state(
        self, device: str, name: str, state: str, timeout: float = 60.0
    ) -> bool:
        """Block until the named property reaches the given state.

        Args:
            device: Device name.
            name: Property name.
            state: Target state string: "Idle", "Ok", "Busy", or "Alert".
            timeout: Maximum seconds to wait. Returns False on timeout.

        Returns:
            True if the state was reached, False on timeout.

        Raises:
            ScriptCancelledError: If the script is cancelled while waiting.
            ValueError: If state is not a valid INDI property state.
        """
        self._require_not_cancelled()
        try:
            target = IndiPropertyState(state)
        except ValueError:
            raise ValueError(
                f"Unknown INDI state '{state}'. Valid values: Idle, Ok, Busy, Alert"
            )

        matched = threading.Event()

        def on_update(prop: IProperty) -> None:
            if prop.device_name == device and prop.name == name:
                if prop.state == target:
                    matched.set()

        unsub = self._bus.subscribe(on_update)
        try:
            # Subscribe first to avoid the race where the update arrives
            # between the current-state check and the first wait() call.
            current = self.get_property(device, name)
            if current is not None and current.state == target:
                return True

            deadline = _time.monotonic() + timeout
            while not matched.is_set():
                remaining = deadline - _time.monotonic()
                if remaining <= 0:
                    return False
                if self._cancel.wait(timeout=min(0.25, remaining)):
                    raise ScriptCancelledError(
                        "Script cancelled during wait_for_state"
                    )
        finally:
            unsub()

        return True

    def wait_for_value(
        self,
        device: str,
        name: str,
        element: str,
        predicate: Callable,
        timeout: float = 60.0,
    ) -> bool:
        """Block until predicate(value) returns True for the named element.

        Args:
            device: Device name.
            name: Property name.
            element: Element name within the property.
            predicate: Callable(value) → bool. Called with float for number
                       elements, str otherwise.
            timeout: Maximum seconds to wait. Returns False on timeout.

        Returns:
            True if predicate was satisfied, False on timeout.

        Raises:
            ScriptCancelledError: If the script is cancelled while waiting.
        """
        self._require_not_cancelled()
        matched = threading.Event()

        def on_update(prop: IProperty) -> None:
            if prop.device_name == device and prop.name == name:
                elem = prop.elements.get(element)
                if elem is not None:
                    val = elem.value
                    if prop.type == IndiPropertyType.NUMBER:
                        try:
                            val = float(val)
                        except (ValueError, TypeError):
                            pass
                    try:
                        if predicate(val):
                            matched.set()
                    except Exception:
                        pass

        unsub = self._bus.subscribe(on_update)
        try:
            current_val = self.get_value(device, name, element)
            if current_val is not None:
                try:
                    if predicate(current_val):
                        return True
                except Exception:
                    pass

            deadline = _time.monotonic() + timeout
            while not matched.is_set():
                remaining = deadline - _time.monotonic()
                if remaining <= 0:
                    return False
                if self._cancel.wait(timeout=min(0.25, remaining)):
                    raise ScriptCancelledError(
                        "Script cancelled during wait_for_value"
                    )
        finally:
            unsub()

        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_not_cancelled(self) -> None:
        if self._cancel.is_set():
            raise ScriptCancelledError("Script was cancelled")

    def _build_prop(
        self,
        device: str,
        name: str,
        prop_type: IndiPropertyType,
        values: dict,
    ) -> IProperty:
        prop = IProperty(
            device_name=device,
            name=name,
            type=prop_type,
            perm=IndiPropertyPerm.RW,
        )
        for elem_name, val in values.items():
            elem = IPropertyElement(name=elem_name, value=str(val))
            prop.elements[elem_name] = elem
        return prop


class TimeScriptApi:
    """Script-facing time utilities. Injected as 'time_utils' into scripts."""

    def __init__(self, cancel_event: threading.Event) -> None:
        self._cancel = cancel_event

    def now(self):
        """Return current time as astropy.time.Time."""
        from astropy.time import Time  # type: ignore
        return Time.now()

    def sleep(self, seconds: float) -> None:
        """Sleep for the given duration. Interruptible by script cancellation.

        Raises:
            ScriptCancelledError: If the script is cancelled during sleep.
        """
        deadline = _time.monotonic() + seconds
        while _time.monotonic() < deadline:
            remaining = deadline - _time.monotonic()
            if self._cancel.wait(timeout=min(0.1, remaining)):
                raise ScriptCancelledError("Script cancelled during sleep")
