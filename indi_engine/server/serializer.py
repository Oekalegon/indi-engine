"""Serializer: converts IProperty and message events to engine protocol JSON dicts.

The engine protocol uses JSON over TCP (newline-delimited). This module handles
the IProperty → dict conversion for the two outbound message types:

  "def" — full property definition including metadata (label, group, perm, format, etc.)
  "set" — current value update; omits metadata, adds target_value per element
  "message" — log/status text from INDI server or engine components
"""

from typing import Optional
from indi_engine.indi.protocol.properties import IDevice, IProperty
from indi_engine.indi.protocol.constants import IndiPropertyType


def serialize_property(prop: IProperty, mode: str) -> dict:
    """Convert an IProperty to a protocol dict.

    Args:
        prop: The property to serialize.
        mode: "def" for a full property definition, "set" for a value update.

    Returns:
        A dict ready for json.dumps.
    """
    result = {
        "type": mode,
        "device": prop.device_name,
        "property": prop.name,
        "data_type": prop.type.value,
        "state": prop.state.value,
        "timestamp": prop.timestamp.isoformat() if prop.timestamp else None,
    }

    if mode == "def":
        result["label"] = prop.label
        result["group"] = prop.group
        result["perm"] = prop.perm.value

    result["elements"] = [
        _serialize_element(elem, prop.type, mode)
        for elem in prop.elements.values()
    ]

    return result


def serialize_message(
    device_name: Optional[str],
    message_text: str,
    timestamp: Optional[str],
    source: Optional[str] = None,
    context: Optional[dict] = None,
) -> dict:
    """Convert a log/status message to a protocol dict.

    Args:
        device_name: INDI device name, or None for server-level messages.
        message_text: The message string.
        timestamp: ISO-format timestamp string, or None.
        source: Engine component name for engine-originated messages (e.g. "imaging-sequencer").
        context: Optional structured metadata dict for engine-originated messages.

    Returns:
        A dict ready for json.dumps.
    """
    result: dict = {
        "type": "message",
        "device": device_name,
        "message": message_text,
        "timestamp": timestamp,
    }
    if source is not None:
        result["source"] = source
    if context is not None:
        result["context"] = context
    return result


def _serialize_element(elem, prop_type: IndiPropertyType, mode: str) -> dict:
    if mode == "def":
        return _serialize_element_def(elem, prop_type)
    return _serialize_element_set(elem, prop_type)


def _serialize_element_def(elem, prop_type: IndiPropertyType) -> dict:
    base = {"name": elem.name, "label": elem.label}

    if prop_type == IndiPropertyType.NUMBER:
        base["format"] = elem.format
        base["min"] = elem.min
        base["max"] = elem.max
        base["step"] = elem.step
        base["value"] = _to_float(elem.value)

    elif prop_type == IndiPropertyType.BLOB:
        pass  # no data in def; name and label are sufficient

    else:
        # TEXT, SWITCH, LIGHT
        base["value"] = elem.value

    return base


def _serialize_element_set(elem, prop_type: IndiPropertyType) -> dict:
    if prop_type == IndiPropertyType.NUMBER:
        return {
            "name": elem.name,
            "value": _to_float(elem.value),
            "target_value": _to_float(elem.target_value) if elem.target_value is not None else None,
        }

    if prop_type == IndiPropertyType.BLOB:
        return {
            "name": elem.name,
            "blob_format": elem.blob_format,
            "blob_size": elem.blob_size,
        }

    # TEXT, SWITCH, LIGHT
    return {
        "name": elem.name,
        "value": elem.value,
        "target_value": elem.target_value,
    }


def serialize_script_status(
    run_id: str,
    name: str,
    status: str,
    message: str = "",
    progress: float = 0.0,
) -> dict:
    """Convert a script execution status event to a protocol dict.

    Args:
        run_id: Unique identifier for the script run.
        name: Script name.
        status: One of "running", "finished", "error", "cancelled".
        message: Human-readable progress or result message.
        progress: Completion fraction in [0.0, 1.0].

    Returns:
        A dict ready for json.dumps.
    """
    return {
        "type": "script_status",
        "run_id": run_id,
        "name": name,
        "status": status,
        "message": message,
        "progress": progress,
    }


def serialize_device_info(device: IDevice) -> dict:
    """Convert an IDevice to a device_info protocol dict.

    Returns a dict containing the device name, connected state, and all
    properties serialized as "def" objects.
    """
    return {
        "type": "device_info",
        "device": device.name,
        "connected": device.isConnected(),
        "properties": [{k: v for k, v in serialize_property(prop, "def").items() if k != "type"} for prop in device.properties.values()],
    }


def _to_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None
