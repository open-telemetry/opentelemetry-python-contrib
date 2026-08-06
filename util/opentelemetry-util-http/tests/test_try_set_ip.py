# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import logging
import socket
import unittest
from http.client import HTTPConnection
from unittest.mock import MagicMock, patch

from opentelemetry.util.http.httplib import trysetip


class TestTrySetIP(unittest.TestCase):
    def setUp(self):
        # Setup a mock HTTPConnection
        self.conn = MagicMock(spec=HTTPConnection)
        self.conn.sock = MagicMock(spec=socket.socket)

        # Mock state function and Span class
        self.mock_state = {"need_ip": [MagicMock()]}
        self.mock_getstate = patch(
            "opentelemetry.util.http.httplib._getstate",
            return_value=self.mock_state,
        )
        self.mock_getstate.start()

    def test_ip_set_successfully(self):
        self.conn.sock.getpeername.return_value = ("192.168.1.1", 8080)

        success = trysetip(self.conn, loglevel=logging.DEBUG)

        # Verify that the IP was set correctly
        for span in self.mock_state["need_ip"]:
            span.set_attribute.assert_called_once_with(
                "net.peer.ip", "192.168.1.1"
            )
        self.assertTrue(success)

    def test_no_socket_connection(self):
        # Setup the connection with no socket
        self.conn.sock = None

        success = trysetip(self.conn, loglevel=logging.DEBUG)

        self.assertFalse(success)

    def test_exception_during_ip_retrieval(self):
        self.conn.sock.getpeername.side_effect = Exception("Test Exception")

        with self.assertLogs(level=logging.WARNING) as warning:
            success = trysetip(self.conn, loglevel=logging.WARNING)
            self.assertEqual(len(warning.records), 1)
            self.assertIn(
                "Failed to get peer address", warning.records[0].message
            )
            self.assertTrue(success)
