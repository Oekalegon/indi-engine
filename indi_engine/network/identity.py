"""Engine identity: stable UUID and human-readable name."""

import logging
import socket
import uuid

logger = logging.getLogger(__name__)


class EngineIdentity:
    """Manages the engine's stable UUID and display name.

    The ID must be set via the ``engine.id`` key in the YAML config so it is
    stable and referenceable by other engines.  If omitted, a random UUID is
    generated for this session only (not persisted) and a warning is logged.
    The name defaults to the machine hostname.
    """

    def __init__(self, engine_id: str = None, name: str = "auto"):
        if engine_id:
            self.id = engine_id
        else:
            self.id = str(uuid.uuid4())
            logger.warning(
                "No engine.id set in config — generated ephemeral UUID %s. "
                "Set engine.id in your YAML to make this stable.",
                self.id,
            )
        self.name = socket.gethostname() if name == "auto" else name
