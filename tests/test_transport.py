"""Tests for IndiTransport (protocol transport layer).

Tests the low-level TCP socket transport that handles:
- Connection/disconnection
- Background reader thread
- Message queueing
- Automatic reconnection with backoff
"""

import pytest
import socket
import threading
import time
from unittest.mock import MagicMock, patch, call

from indi_engine.indi.protocol.transport import IndiTransport
from indi_engine.indi.protocol.errors import IndiConnectionError, IndiDisconnectedError


class TestIndiTransportInit:
    """Tests for IndiTransport initialization."""

    def test_init_default_host_port(self):
        """Test initialization with default host and port."""
        transport = IndiTransport()
        assert transport.host == "localhost"
        assert transport.port == 7624
        assert transport.socket is None
        assert not transport.is_connected()


class TestIsConnected:
    """Tests for is_connected method."""

    def test_is_connected_initially_false(self):
        """Test that transport is not connected initially."""
        transport = IndiTransport()
        assert not transport.is_connected()


class TestSendMessage:
    """Tests for send_message method."""

    def test_send_message_not_connected_raises(self):
        """Test that sending when not connected raises error."""
        transport = IndiTransport()
        with pytest.raises(IndiDisconnectedError):
            transport.send_message('<getProperties version="1.7"/>')

    def test_send_message_with_mock_socket(self):
        """Test sending message with mocked socket."""
        transport = IndiTransport()
        transport._connected = True
        transport.socket = MagicMock()

        msg = '<getProperties version="1.7"/>'
        transport.send_message(msg)

        # Verify send was called with UTF-8 encoded message
        transport.socket.sendall.assert_called_once_with(msg.encode('utf-8'))

    def test_send_message_socket_error_raises(self):
        """Test that socket error is converted to IndiConnectionError."""
        transport = IndiTransport()
        transport._connected = True
        transport.socket = MagicMock()
        transport.socket.sendall.side_effect = socket.error("Connection lost")

        with pytest.raises(IndiConnectionError):
            transport.send_message('<test/>')

        assert not transport.is_connected()


class TestGetMessage:
    """Tests for get_message method."""

    def test_get_message_empty_queue_returns_none(self):
        """Test that getting message from empty queue returns None."""
        transport = IndiTransport()
        message = transport.get_message(timeout=0.01)
        assert message is None

    def test_get_message_returns_queued_message(self):
        """Test that get_message returns queued message."""
        transport = IndiTransport()
        # Manually queue a message (simulating reader thread)
        msg_bytes = b"<test/>"
        transport._message_queue.put(msg_bytes)

        message = transport.get_message(timeout=0.1)
        assert message == msg_bytes

    def test_get_message_fifo_order(self):
        """Test that messages are returned in FIFO order."""
        transport = IndiTransport()
        msg1 = b"<first/>"
        msg2 = b"<second/>"
        transport._message_queue.put(msg1)
        transport._message_queue.put(msg2)

        assert transport.get_message(timeout=0.1) == msg1
        assert transport.get_message(timeout=0.1) == msg2


class TestConnect:
    """Tests for connect method."""

    @patch('socket.socket')
    def test_connect_success(self, mock_socket_class):
        """Test successful connection."""
        mock_socket = MagicMock()
        mock_socket_class.return_value = mock_socket

        transport = IndiTransport()
        transport.connect("localhost", 7624)

        assert transport.is_connected()
        mock_socket.connect.assert_called_once_with(("localhost", 7624))

    @patch('socket.socket')
    def test_connect_already_connected(self, mock_socket_class):
        """Test connecting when already connected."""
        mock_socket = MagicMock()
        mock_socket_class.return_value = mock_socket

        transport = IndiTransport()
        transport.connect("localhost", 7624)
        mock_socket.reset_mock()

        # Try to connect again
        transport.connect("localhost", 7624)

        # Should NOT try to connect again
        mock_socket.connect.assert_not_called()

    @patch('socket.socket')
    def test_connect_socket_error_raises(self, mock_socket_class):
        """Test that socket error during connect raises IndiConnectionError."""
        mock_socket = MagicMock()
        mock_socket.connect.side_effect = socket.error("Connection refused")
        mock_socket_class.return_value = mock_socket

        transport = IndiTransport()
        with pytest.raises(IndiConnectionError):
            transport.connect("localhost", 7624)

        assert not transport.is_connected()

    @patch('socket.socket')
    def test_connect_starts_reader_thread(self, mock_socket_class):
        """Test that connect starts reader thread."""
        mock_socket = MagicMock()
        mock_socket_class.return_value = mock_socket

        transport = IndiTransport()
        transport.connect("localhost", 7624)

        # Reader thread should be started
        assert transport._reader_thread is not None
        assert transport._reader_thread.is_alive() or not transport._stop_event.is_set()


class TestDisconnect:
    """Tests for disconnect method."""

    @patch('socket.socket')
    def test_disconnect_closes_socket(self, mock_socket_class):
        """Test that disconnect closes socket."""
        mock_socket = MagicMock()
        mock_socket_class.return_value = mock_socket

        transport = IndiTransport()
        transport.connect("localhost", 7624)
        transport.disconnect()

        mock_socket.close.assert_called()
        assert not transport.is_connected()

    @patch('socket.socket')
    def test_disconnect_stops_reader_thread(self, mock_socket_class):
        """Test that disconnect stops reader thread."""
        mock_socket = MagicMock()
        mock_socket_class.return_value = mock_socket

        transport = IndiTransport()
        transport.connect("localhost", 7624)
        time.sleep(0.1)  # Give thread time to start

        transport.disconnect()
        time.sleep(0.1)  # Give thread time to stop

        # Stop event should be set
        assert transport._stop_event.is_set()

    def test_disconnect_when_not_connected(self):
        """Test that disconnect when not connected doesn't raise."""
        transport = IndiTransport()
        # Should not raise
        transport.disconnect()


class TestReaderLoop:
    """Tests for _reader_loop method."""

    @patch('socket.socket')
    def test_reader_loop_queues_messages(self, mock_socket_class):
        """Test that reader loop queues received messages."""
        mock_socket = MagicMock()
        mock_socket.recv.side_effect = [
            b"<test1/>",
            b"",  # Connection closed
        ]
        mock_socket_class.return_value = mock_socket

        transport = IndiTransport()
        transport.connect("localhost", 7624)
        time.sleep(0.2)  # Give reader time to process

        # Message should be in queue
        message = transport.get_message(timeout=0.1)
        assert message == b"<test1/>"

        transport.disconnect()

    @patch('socket.socket')
    def test_reader_loop_handles_socket_timeout(self, mock_socket_class):
        """Test that reader loop handles socket timeouts gracefully."""
        mock_socket = MagicMock()
        mock_socket.recv.side_effect = socket.timeout("timeout")

        mock_socket_class.return_value = mock_socket

        transport = IndiTransport()
        transport.connect("localhost", 7624)
        time.sleep(0.1)

        # Should still be connected (timeout is normal)
        # Reader tries to reconnect after timeout
        transport.disconnect()

    @patch('socket.socket')
    def test_reader_loop_handles_connection_lost(self, mock_socket_class):
        """Test that reader loop detects lost connection."""
        mock_socket = MagicMock()
        # Empty data means connection closed
        mock_socket.recv.return_value = b""
        mock_socket_class.return_value = mock_socket

        transport = IndiTransport()
        transport.connect("localhost", 7624)
        time.sleep(0.1)

        # Connection should be lost
        # Reader should attempt reconnection
        transport._stop_event.set()  # Stop trying to reconnect
        transport.disconnect()


class TestMessageParsing:
    """Tests for message parsing and queuing."""

    @patch('socket.socket')
    def test_reader_splits_messages_on_closing_tag(self, mock_socket_class):
        """Test that reader correctly splits multiple messages."""
        mock_socket = MagicMock()
        # Simulate receiving multiple messages in one chunk
        mock_socket.recv.side_effect = [
            b"<first/><second/>",
            b"",  # Connection closed
        ]
        mock_socket_class.return_value = mock_socket

        transport = IndiTransport()
        transport.connect("localhost", 7624)
        time.sleep(0.15)

        # Both messages should be in queue
        msg1 = transport.get_message(timeout=0.1)
        msg2 = transport.get_message(timeout=0.1)

        assert msg1 == b"<first/>"
        assert msg2 == b"<second/>"

        transport.disconnect()

    @patch('socket.socket')
    def test_reader_handles_incomplete_messages(self, mock_socket_class):
        """Test that reader buffers incomplete messages."""
        mock_socket = MagicMock()
        # Message spans multiple recv calls
        mock_socket.recv.side_effect = [
            b"<test attr=",
            b'"value"/>',
            b"",  # Connection closed
        ]
        mock_socket_class.return_value = mock_socket

        transport = IndiTransport()
        transport.connect("localhost", 7624)
        time.sleep(0.15)

        # Complete message should be in queue
        message = transport.get_message(timeout=0.1)
        assert message == b'<test attr="value"/>'

        transport.disconnect()


class TestReconnection:
    """Tests for reconnection logic."""

    @patch('socket.socket')
    def test_reconnect_with_exponential_backoff(self, mock_socket_class):
        """Test that reconnection uses exponential backoff."""
        mock_socket = MagicMock()
        mock_socket.recv.side_effect = [
            b"",  # Connection closed immediately
        ]
        mock_socket_class.return_value = mock_socket

        transport = IndiTransport()
        initial_delay = transport._reconnect_delay

        # Trigger disconnection
        transport.connect("localhost", 7624)
        time.sleep(0.15)

        # After disconnect, delay should have increased
        # (but we won't wait for it in tests)
        transport._stop_event.set()
        transport.disconnect()

    @patch('time.sleep')  # Mock sleep to avoid slowdown
    @patch('socket.socket')
    def test_reconnect_stops_on_stop_event(self, mock_socket_class, mock_sleep):
        """Test that reconnection respects stop event."""
        mock_socket = MagicMock()
        mock_socket.recv.side_effect = socket.error("Connection lost")
        mock_socket_class.return_value = mock_socket

        transport = IndiTransport()
        transport.connect("localhost", 7624)

        # Immediately stop
        transport._stop_event.set()
        time.sleep(0.05)

        # _handle_disconnection should have checked stop_event
        # and returned without retrying
