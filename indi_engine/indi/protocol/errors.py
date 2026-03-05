"""INDI protocol custom exceptions."""


class IndiError(Exception):
    """Base exception for all INDI-related errors."""
    pass


class IndiConnectionError(IndiError):
    """Raised when INDI server connection fails."""
    pass


class IndiProtocolError(IndiError):
    """Raised when INDI protocol parsing or validation fails."""
    pass


class IndiTimeoutError(IndiError):
    """Raised when an INDI operation times out."""
    pass


class IndiDisconnectedError(IndiError):
    """Raised when an operation is attempted while disconnected."""
    pass
