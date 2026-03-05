"""INDI protocol TCP socket transport layer.

Handles:
- TCP socket connection/disconnection
- Background reader thread for non-blocking I/O
- Automatic reconnection with exponential backoff
- Thread-safe message queueing
"""

import socket
import threading
import logging
import time
from queue import Queue, Empty
from typing import Optional

from .constants import (
    INDI_HOST_DEFAULT,
    INDI_PORT_DEFAULT,
    SOCKET_TIMEOUT,
    RECONNECT_MIN_DELAY,
    RECONNECT_MAX_DELAY,
    RECONNECT_BACKOFF_FACTOR,
)
from .errors import IndiConnectionError, IndiDisconnectedError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# XML stream splitter
#
# The INDI server sends a continuous stream of top-level XML elements with no
# document wrapper or length framing.  We must detect complete element
# boundaries ourselves by tracking tag nesting depth and respecting quoted
# attribute values.
# ---------------------------------------------------------------------------

def _find_gt(buf: bytes, pos: int) -> int:
    """Return index of the next '>' that is not inside a quoted string."""
    n = len(buf)
    while pos < n:
        c = buf[pos]
        if c == ord('"'):
            pos += 1
            while pos < n and buf[pos] != ord('"'):
                pos += 1
            if pos >= n:
                return -1
        elif c == ord("'"):
            pos += 1
            while pos < n and buf[pos] != ord("'"):
                pos += 1
            if pos >= n:
                return -1
        elif c == ord('>'):
            return pos
        pos += 1
    return -1


def _find_tag_gt(buf: bytes, pos: int) -> tuple:
    """Scan from pos (inside an opening tag) to its closing '>'.

    Returns (gt_index, is_self_closing).  gt_index is -1 if not found.
    """
    n = len(buf)
    while pos < n:
        c = buf[pos]
        if c == ord('"'):
            pos += 1
            while pos < n and buf[pos] != ord('"'):
                pos += 1
            if pos >= n:
                return -1, False
        elif c == ord("'"):
            pos += 1
            while pos < n and buf[pos] != ord("'"):
                pos += 1
            if pos >= n:
                return -1, False
        elif c == ord('/') and pos + 1 < n and buf[pos + 1] == ord('>'):
            return pos + 1, True   # self-closing
        elif c == ord('>'):
            return pos, False
        pos += 1
    return -1, False


def _find_element_end(buf: bytes, start: int) -> tuple:
    """Find the end of the XML element whose '<' is at buf[start].

    Returns (end_pos, is_complete) where end_pos is the index after the
    final '>' of the element.  is_complete is False when more data is needed.
    """
    n = len(buf)
    depth = 0
    pos = start

    while pos < n:
        if buf[pos] != ord('<'):
            pos += 1
            continue

        # XML comment
        if buf[pos:pos + 4] == b'<!--':
            end = buf.find(b'-->', pos + 4)
            if end == -1:
                return start, False
            pos = end + 3
            continue

        # Processing instruction
        if buf[pos:pos + 2] == b'<?':
            end = buf.find(b'?>', pos + 2)
            if end == -1:
                return start, False
            pos = end + 2
            continue

        # Closing tag
        if buf[pos:pos + 2] == b'</':
            gt = _find_gt(buf, pos + 2)
            if gt == -1:
                return start, False
            depth -= 1
            pos = gt + 1
            if depth == 0:
                return pos, True
            continue

        # Opening tag (possibly self-closing)
        gt, self_closing = _find_tag_gt(buf, pos + 1)
        if gt == -1:
            return start, False
        if self_closing:
            if depth == 0:
                return gt + 1, True
            pos = gt + 1
        else:
            depth += 1
            pos = gt + 1

    return start, False


def _split_xml_messages(buf: bytes) -> tuple:
    """Split an INDI XML stream buffer into complete top-level XML elements.

    Returns (messages, remaining_buffer).
    """
    messages = []
    pos = 0
    n = len(buf)

    while pos < n:
        # Skip inter-message whitespace
        while pos < n and buf[pos:pos + 1] in (b' ', b'\t', b'\n', b'\r'):
            pos += 1
        if pos >= n:
            break

        if buf[pos:pos + 1] != b'<':
            pos += 1   # malformed stream: skip byte
            continue

        end, complete = _find_element_end(buf, pos)
        if not complete:
            break      # wait for more data

        msg = buf[pos:end].strip()
        if msg:
            messages.append(msg)
        pos = end

    return messages, buf[pos:]


class IndiTransport:
    """TCP socket transport for INDI protocol.

    Manages connection lifecycle and non-blocking message I/O via a background thread.
    Automatically reconnects on connection loss with exponential backoff.
    """

    def __init__(self):
        self.host = INDI_HOST_DEFAULT
        self.port = INDI_PORT_DEFAULT
        self.socket: Optional[socket.socket] = None
        self._lock = threading.Lock()
        self._message_queue: Queue = Queue()
        self._reader_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._connected = False
        self._reconnect_delay = RECONNECT_MIN_DELAY
        self.logger = logger

    def connect(self, host: str = INDI_HOST_DEFAULT, port: int = INDI_PORT_DEFAULT) -> None:
        """Connect to INDI server and start reader thread.

        Args:
            host: INDI server hostname
            port: INDI server port

        Raises:
            IndiConnectionError: If connection fails
        """
        self.host = host
        self.port = port
        self._stop_event.clear()
        self._reconnect_delay = RECONNECT_MIN_DELAY

        with self._lock:
            if self._connected:
                self.logger.warning(f"Already connected to {self.host}:{self.port}")
                return

            try:
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.settimeout(SOCKET_TIMEOUT)
                self.logger.info(f"Connecting to INDI server at {self.host}:{self.port}...")
                self.socket.connect((self.host, self.port))
                self._connected = True
                self.logger.info(f"Connected to INDI server at {self.host}:{self.port}")
                self._reconnect_delay = RECONNECT_MIN_DELAY  # Reset on successful connection

            except socket.error as e:
                self._connected = False
                raise IndiConnectionError(f"Failed to connect to {self.host}:{self.port}: {e}")

        # Start reader thread
        self._stop_event.clear()
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()

    def disconnect(self) -> None:
        """Disconnect from INDI server and stop reader thread."""
        self._stop_event.set()

        # Wait for reader thread to stop
        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=5)

        with self._lock:
            if self.socket:
                try:
                    self.socket.close()
                except Exception as e:
                    self.logger.warning(f"Error closing socket: {e}")
                finally:
                    self.socket = None
            self._connected = False

        self.logger.info("Disconnected from INDI server")

    def send_message(self, xml_string: str) -> None:
        """Send an XML message to the server.

        Args:
            xml_string: XML message to send

        Raises:
            IndiDisconnectedError: If not connected
        """
        if not self._connected:
            raise IndiDisconnectedError("Not connected to INDI server")

        with self._lock:
            if not self.socket:
                raise IndiDisconnectedError("Socket is closed")

            try:
                self.socket.sendall(xml_string.encode('utf-8'))
            except socket.error as e:
                self._connected = False
                raise IndiConnectionError(f"Failed to send message: {e}")

    def get_message(self, timeout: float = 0.1) -> Optional[bytes]:
        """Get next message from queue (non-blocking).

        Args:
            timeout: Queue timeout in seconds

        Returns:
            Message bytes if available, None if queue is empty
        """
        try:
            return self._message_queue.get(timeout=timeout)
        except Empty:
            return None

    def is_connected(self) -> bool:
        """Check if connected to server."""
        return self._connected

    def _reader_loop(self) -> None:
        """Background thread that reads from socket and queues messages.

        Runs until _stop_event is set or connection is lost.
        Handles reconnection with exponential backoff.
        """
        buffer = b""

        while not self._stop_event.is_set():
            try:
                if not self._connected or not self.socket:
                    self._handle_disconnection()
                    continue

                # Try to read data from socket
                try:
                    data = self.socket.recv(4096)
                    if not data:
                        # Connection closed by server
                        self.logger.info("INDI server closed connection")
                        self._connected = False
                        self._handle_disconnection()
                        continue

                    buffer += data

                    # Extract complete top-level XML elements from the stream
                    messages, buffer = _split_xml_messages(buffer)
                    for message_bytes in messages:
                        self._message_queue.put(message_bytes)

                except socket.timeout:
                    # Timeout is expected, just continue
                    continue

                except socket.error as e:
                    self.logger.warning(f"Socket error: {e}")
                    self._connected = False
                    self._handle_disconnection()
                    continue

            except Exception as e:
                self.logger.error(f"Unexpected error in reader loop: {e}")
                self._connected = False
                self._handle_disconnection()

    def _handle_disconnection(self) -> None:
        """Handle disconnection and attempt reconnection with backoff."""
        if self._stop_event.is_set():
            return

        self._connected = False
        delay = self._reconnect_delay

        self.logger.warning(f"Attempting to reconnect in {delay} seconds...")
        time.sleep(delay)

        # Exponential backoff
        self._reconnect_delay = min(
            self._reconnect_delay * RECONNECT_BACKOFF_FACTOR,
            RECONNECT_MAX_DELAY
        )

        # Try to reconnect
        try:
            with self._lock:
                if self.socket:
                    try:
                        self.socket.close()
                    except Exception:
                        pass
                    self.socket = None

                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.settimeout(SOCKET_TIMEOUT)
                self.socket.connect((self.host, self.port))
                self._connected = True
                self._reconnect_delay = RECONNECT_MIN_DELAY  # Reset on success
                self.logger.info(f"Reconnected to INDI server")

        except socket.error as e:
            self.logger.warning(f"Reconnection failed: {e}")
            self._connected = False
            # Loop will retry after another delay
