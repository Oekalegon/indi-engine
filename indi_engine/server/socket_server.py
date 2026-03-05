# TODO: Implement JSON socket server for client communication.
# Clients will connect here to:
#   - Query device state
#   - List available actions
#   - Subscribe to property updates
#   - Trigger actions


class SocketServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 8624):
        self.host = host
        self.port = port

    def start(self):
        raise NotImplementedError
