# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from unittest import mock

from opentelemetry.instrumentation.dbapi import (
    BaseTracedConnectionProxy,
    BaseTracedCursorProxy,
)
from opentelemetry.test.test_base import TestBase


class TestDBApiBaseClasses(TestBase):
    class TestConnectionProxy(BaseTracedConnectionProxy):
        def cursor(self, *args, **kwargs):
            return "foo-cursor"

    def test_base_traced_connection_proxy_init(self):
        mock_connection = mock.Mock()
        proxy = self.TestCursorProxy(mock_connection)
        self.assertIs(proxy.__wrapped__, mock_connection)

    def test_base_traced_connection_proxy_getattr_direct_attr(self):
        mock_connection = mock.Mock()
        proxy = self.TestConnectionProxy(mock_connection)
        proxy.foo_attribute = "bar"  # pylint: disable=attribute-defined-outside-init
        self.assertEqual(proxy.foo_attribute, "bar")

    def test_base_traced_connection_proxy_getattr_cnx_attr(self):
        mock_connection = mock.Mock()
        mock_connection.foo_attribute = "bar"
        proxy = self.TestConnectionProxy(mock_connection)
        self.assertEqual(proxy.foo_attribute, "bar")

    def test_base_traced_connection_proxy_cursor(self):
        assert self.TestConnectionProxy("foo-cnx").cursor() == "foo-cursor"

    def test_base_traced_connection_proxy_enter(self):
        mock_connection = mock.Mock()
        mock_connection.__enter__ = mock.Mock()
        mock_connection.__exit__ = mock.Mock()
        proxy = self.TestConnectionProxy(mock_connection)
        with proxy:
            mock_connection.__enter__.assert_called_once()

    def test_base_traced_connection_proxy_exit(self):
        mock_connection = mock.Mock()
        mock_connection.__enter__ = mock.Mock()
        mock_connection.__exit__ = mock.Mock()
        proxy = self.TestConnectionProxy(mock_connection)
        with proxy:
            pass
        mock_connection.__exit__.assert_called_once()

    class TestCursorProxy(BaseTracedCursorProxy):
        def __init__(self, cursor, *args, **kwargs):
            super().__init__(cursor, *args, **kwargs)
            self._cursor_tracer = kwargs.get("test_cursor_tracer", "foo")

    def test_base_traced_cursor_proxy_init(self):
        mock_cursor = mock.Mock()
        mock_cursor_tracer = mock.Mock()
        proxy = self.TestCursorProxy(
            mock_cursor,
            test_cursor_tracer=mock_cursor_tracer,
        )
        self.assertIs(proxy.__wrapped__, mock_cursor)
        assert proxy._cursor_tracer == mock_cursor_tracer

    def test_base_traced_cursor_proxy_callproc(self):
        mock_cursor = mock.Mock()
        mock_cursor.callproc = mock.Mock()
        mock_cursor_tracer = mock.Mock()
        mock_cursor_tracer.traced_execution = mock.Mock()
        proxy = self.TestCursorProxy(
            mock_cursor,
            test_cursor_tracer=mock_cursor_tracer,
        )
        args = ("foo_name",)
        kwargs = {"foo": "bar"}
        proxy.callproc(*args, **kwargs)
        mock_cursor_tracer.traced_execution.assert_called_once_with(
            mock_cursor, mock_cursor.callproc, *args, **kwargs
        )

    def test_base_traced_cursor_proxy_execute(self):
        mock_cursor = mock.Mock()
        mock_cursor.execute = mock.Mock()
        mock_cursor_tracer = mock.Mock()
        mock_cursor_tracer.traced_execution = mock.Mock()
        proxy = self.TestCursorProxy(
            mock_cursor,
            test_cursor_tracer=mock_cursor_tracer,
        )
        args = ("foo_name",)
        kwargs = {"foo": "bar"}
        proxy.execute(*args, **kwargs)
        mock_cursor_tracer.traced_execution.assert_called_once_with(
            mock_cursor, mock_cursor.execute, *args, **kwargs
        )

    def test_base_traced_cursor_proxy_executemany(self):
        mock_cursor = mock.Mock()
        mock_cursor.executemany = mock.Mock()
        mock_cursor_tracer = mock.Mock()
        mock_cursor_tracer.traced_execution = mock.Mock()
        proxy = self.TestCursorProxy(
            mock_cursor,
            test_cursor_tracer=mock_cursor_tracer,
        )
        args = ("foo_name",)
        kwargs = {"foo": "bar"}
        proxy.executemany(*args, **kwargs)
        mock_cursor_tracer.traced_execution.assert_called_once_with(
            mock_cursor, mock_cursor.executemany, *args, **kwargs
        )

    def test_base_traced_cursor_proxy_enter(self):
        mock_cursor = mock.Mock()
        mock_cursor.__enter__ = mock.Mock()
        mock_cursor.__exit__ = mock.Mock()
        proxy = self.TestCursorProxy(mock_cursor)
        with proxy:
            mock_cursor.__enter__.assert_called_once()

    def test_base_traced_cursor_proxy_exit(self):
        mock_cursor = mock.Mock()
        mock_cursor.__enter__ = mock.Mock()
        mock_cursor.__exit__ = mock.Mock()
        proxy = self.TestCursorProxy(mock_cursor)
        with proxy:
            pass
        mock_cursor.__exit__.assert_called_once()
