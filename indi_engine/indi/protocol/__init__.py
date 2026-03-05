"""Pure Python INDI protocol implementation.

This module provides a pure Python implementation of the INDI protocol,
eliminating the need for pyindi-client and its SWIG-wrapped C++ dependencies.

Components:
- constants: INDI protocol constants and enums
- errors: Custom exception types
- properties: Property/Device/Element object models
- parser: XML message parsing
- state: Device/property state tracking and change detection
- transport: TCP socket communication with reconnection
- client: Main IndiClient class orchestrating all layers
"""

from .client import PurePythonIndiClient
from .errors import IndiError, IndiConnectionError, IndiProtocolError
from .properties import IDevice, IProperty, IPropertyElement

__all__ = [
    "PurePythonIndiClient",
    "IndiError",
    "IndiConnectionError",
    "IndiProtocolError",
    "IDevice",
    "IProperty",
    "IPropertyElement",
]
