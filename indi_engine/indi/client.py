"""INDI client implementation.

Pure Python implementation without libindi or pyindi-client dependencies.
Maintains the same interface as the original PyIndi.BaseClient-based client.
"""

import logging
from .protocol.client import PurePythonIndiClient
from .protocol.constants import IndiPropertyType

logger = logging.getLogger(__name__)


class IndiClient(PurePythonIndiClient):
    """INDI client using pure Python protocol implementation.

    This class extends PurePythonIndiClient to maintain backward compatibility
    with existing code while providing logging and callbacks.
    """

    def __init__(self, host: str = "localhost", port: int = 7624, state_manager=None):
        """Initialize INDI client.

        Args:
            host: INDI server hostname (default: localhost)
            port: INDI server port (default: 7624)
            state_manager: Optional DeviceStateManager for state synchronization
        """
        super().__init__(host, port, state_manager)
        # Override default callbacks with logging versions
        self.setup_callbacks()

    def setup_callbacks(self) -> None:
        """Setup logging callbacks."""
        # Bind callbacks to methods
        self.newDevice = self._logged_newDevice
        self.removeDevice = self._logged_removeDevice
        self.newProperty = self._logged_newProperty
        self.removeProperty = self._logged_removeProperty
        self.updateProperty = self._logged_updateProperty
        self.newMessage = self._logged_newMessage
        self.serverConnected = self._logged_serverConnected
        self.serverDisconnected = self._logged_serverDisconnected

    def _logged_newDevice(self, d):
        """Log new device."""
        logger.info("New device: %s", d.getDeviceName())

    def _logged_removeDevice(self, d):
        """Log device removal."""
        logger.info("Device removed: %s", d.getDeviceName())

    def _logged_newProperty(self, p):
        """Log new property."""
        device = p.getDeviceName()
        name = p.getName()
        logger.debug("New property: %s / %s", device, name)
        # State manager update is handled by parent class

    def _logged_removeProperty(self, p):
        """Log property removal."""
        device = p.getDeviceName()
        name = p.getName()
        logger.debug("Property removed: %s / %s", device, name)
        # State manager removal is handled by parent class

    def _logged_updateProperty(self, p):
        """Log property update."""
        device = p.getDeviceName()
        name = p.getName()
        logger.debug("Property updated: %s / %s", device, name)
        # State manager update is handled by parent class

    def _logged_newMessage(self, d, m):
        """Log message from device."""
        logger.info("Message [%s]: %s", d.getDeviceName(), m)

    def _logged_serverConnected(self):
        """Log server connected."""
        logger.info("Connected to INDI server at %s:%d", self.getHost(), self.getPort())

    def _logged_serverDisconnected(self, code):
        """Log server disconnected."""
        logger.warning("Disconnected from INDI server (code %d)", code)


def _extract_value(p):
    """Return a simple representation of a property's current value(s).

    This is a helper function for backward compatibility.
    Works with the new IProperty objects from protocol.properties.
    """
    try:
        prop_type = p.getType()

        if prop_type == IndiPropertyType.NUMBER:
            elements = p.getNumber()
            if elements:
                return {v.getName(): v.getValue() for v in elements}

        elif prop_type == IndiPropertyType.TEXT:
            elements = p.getText()
            if elements:
                return {v.getName(): v.getText() for v in elements}

        elif prop_type == IndiPropertyType.SWITCH:
            elements = p.getSwitch()
            if elements:
                return {v.getName(): v.getValue() for v in elements}

        elif prop_type == IndiPropertyType.LIGHT:
            elements = p.getLight()
            if elements:
                return {v.getName(): v.getValue() for v in elements}

    except Exception as e:
        logger.debug(f"Error extracting value from property: {e}")

    return None
