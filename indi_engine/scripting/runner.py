"""Script runner: executes sandboxed scripts and manages their lifecycle.

Each run gets a unique run_id, a cancellation event, and broadcasts
script_status messages via the engine's broadcast function.
"""

import logging
import math as _math
import threading
import time as _time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Optional

from indi_engine.scripting.sandbox import compile_script, make_restricted_globals
from indi_engine.scripting.api import (
    IndiScriptApi,
    TimeScriptApi,
    PropertyUpdateBus,
    ScriptCancelledError,
    ScriptPausedError,
)
from indi_engine.scripting.registry import ScriptRegistry
from indi_engine.server.serializer import serialize_script_status

logger = logging.getLogger(__name__)


@dataclass
class _RunHandle:
    run_id: str
    name: str
    cancel_event: threading.Event
    pause_immediate_event: threading.Event
    pause_deferred_event: threading.Event
    started_at: float = field(default_factory=_time.monotonic)


class ScriptRunner:
    """Manages compilation, execution, and lifecycle of user scripts.

    Args:
        registry: ScriptRegistry for loading script source.
        indi_client: PurePythonIndiClient passed to IndiScriptApi.
        update_bus: PropertyUpdateBus for wait_for_state/value support.
        broadcast_fn: Called with a dict to broadcast messages to all clients.
        max_workers: Maximum number of concurrently running scripts.
        default_timeout: Hard wall-clock limit per run (seconds).
    """

    def __init__(
        self,
        registry: ScriptRegistry,
        indi_client,
        update_bus: PropertyUpdateBus,
        broadcast_fn: Callable[[dict], None],
        max_workers: int = 4,
        default_timeout: float = 3600.0,
    ) -> None:
        self._registry = registry
        self._client = indi_client
        self._bus = update_bus
        self._broadcast = broadcast_fn
        self._default_timeout = default_timeout
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="script"
        )
        self._runs: dict[str, _RunHandle] = {}
        self._runs_lock = threading.Lock()
        # Maps CCD device name → run_id for the script that called enable_blobs().
        # Cleared automatically when the run finishes.
        self._blob_registry: dict[str, str] = {}
        self._blob_registry_lock = threading.Lock()

    @property
    def registry(self) -> ScriptRegistry:
        return self._registry

    def run(self, name: str, params: Optional[dict] = None) -> str:
        """Compile and submit a script for execution.

        Args:
            name: Script name (looked up in registry).
            params: Optional dict passed as 'params' inside the script.

        Returns:
            run_id: Unique identifier for this execution.
        """
        source = self._registry.load(name)
        code = compile_script(source, filename=name + ".py")
        run_id = uuid.uuid4().hex
        cancel_event = threading.Event()
        pause_immediate_event = threading.Event()
        pause_deferred_event = threading.Event()

        handle = _RunHandle(
            run_id=run_id,
            name=name,
            cancel_event=cancel_event,
            pause_immediate_event=pause_immediate_event,
            pause_deferred_event=pause_deferred_event,
        )
        with self._runs_lock:
            self._runs[run_id] = handle

        self._broadcast(
            serialize_script_status(run_id, name, "running", "Script started", 0.0)
        )

        def log(message: str, progress: float = 0.0) -> None:
            self._broadcast(
                serialize_script_status(run_id, name, "running", message, progress)
            )

        future = self._executor.submit(
            self._execute, run_id, name, code, params or {},
            cancel_event, pause_immediate_event, pause_deferred_event, log
        )
        future.add_done_callback(lambda f: self._on_done(f, run_id, name))
        return run_id

    def cancel(self, run_id: str) -> bool:
        """Request cancellation of a running script.

        Returns:
            True if the run_id was found (cancellation requested),
            False if the run_id is unknown or already finished.
        """
        with self._runs_lock:
            handle = self._runs.get(run_id)
        if handle:
            handle.cancel_event.set()
            return True
        return False

    def pause(self, run_id: str, finish_current: bool = True) -> bool:
        """Request a pause of a running script.

        Args:
            run_id: The run to pause.
            finish_current: If True, the script pauses at its next checkpoint()
                call (i.e. after finishing the current unit of work such as an
                exposure). If False, the script is interrupted immediately
                during the next wait_for_state, wait_for_value, or sleep call.

        Returns:
            True if the run_id was found, False if unknown or already finished.
        """
        with self._runs_lock:
            handle = self._runs.get(run_id)
        if not handle:
            return False
        if finish_current:
            handle.pause_deferred_event.set()
        else:
            handle.pause_immediate_event.set()
        return True

    def register_blob_device(
        self, device: str, run_id: str, capture_params: dict | None = None
    ) -> None:
        """Called by IndiScriptApi.enable_blobs() to claim a device for a run."""
        with self._blob_registry_lock:
            self._blob_registry[device] = {
                "run_id": run_id,
                "capture_params": capture_params or {},
            }

    def get_blob_context_for_device(self, device: str) -> dict | None:
        """Return {run_id, capture_params} for the device, or None."""
        with self._blob_registry_lock:
            return self._blob_registry.get(device)

    def list_runs(self) -> list:
        """Return a list of currently active runs."""
        with self._runs_lock:
            return [
                {"run_id": h.run_id, "name": h.name, "status": "running"}
                for h in self._runs.values()
            ]

    def shutdown(self) -> None:
        """Cancel all active runs and shut down the executor."""
        with self._runs_lock:
            handles = list(self._runs.values())
        for h in handles:
            h.cancel_event.set()
        self._executor.shutdown(wait=False)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _execute(
        self,
        run_id: str,
        name: str,
        code,
        params: dict,
        cancel_event: threading.Event,
        pause_immediate_event: threading.Event,
        pause_deferred_event: threading.Event,
        log: Callable,
    ) -> None:
        api = IndiScriptApi(
            self._client,
            self._bus,
            cancel_event,
            run_id=run_id,
            blob_register=self.register_blob_device,
            pause_immediate=pause_immediate_event,
            pause_deferred=pause_deferred_event,
        )
        time_api = TimeScriptApi(
            cancel_event,
            pause_immediate=pause_immediate_event,
            get_checkpoint=lambda: api._last_checkpoint,
        )
        g = make_restricted_globals({
            "indi": api,
            "time_utils": time_api,
            "log": log,
            "params": params,
            "math": _math,
        })
        exec(code, g)  # noqa: S102

    def _on_done(self, future, run_id: str, name: str) -> None:
        with self._runs_lock:
            self._runs.pop(run_id, None)
        with self._blob_registry_lock:
            stale = [d for d, ctx in self._blob_registry.items() if ctx["run_id"] == run_id]
            for d in stale:
                del self._blob_registry[d]
        try:
            future.result()
            self._broadcast(
                serialize_script_status(run_id, name, "finished", "Script completed", 1.0)
            )
        except ScriptCancelledError:
            self._broadcast(
                serialize_script_status(run_id, name, "cancelled", "Script cancelled", 0.0)
            )
        except ScriptPausedError as e:
            resume_command = None
            if e.resume_params is not None:
                resume_command = {
                    "type": "script_control",
                    "action": "run",
                    "name": name,
                    "params": e.resume_params,
                }
            self._broadcast(
                serialize_script_status(run_id, name, "paused", "Script paused", 0.0,
                                        resume_command=resume_command)
            )
        except Exception as e:
            logger.error("Script '%s' (run %s) failed: %s", name, run_id, e)
            self._broadcast(
                serialize_script_status(run_id, name, "error", str(e), 0.0)
            )
