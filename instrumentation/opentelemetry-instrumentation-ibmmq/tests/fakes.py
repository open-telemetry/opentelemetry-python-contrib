# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
"""Fake ibmmq/pymqi client doubles shared by the ibmmq instrumentation tests.

Neither the real ``ibmmq`` package nor the real ``pymqi`` package is
installed in CI (no MQ broker, no native MQI client library on the test
host), so these doubles mirror just enough of both client APIs' shape to
drive the instrumentation code under test.
"""

# The fakes copy the real ibmmq and pymqi APIs verbatim, which means camelCase
# attribute and argument names, a keyword argument ahead of *opts, and private
# members that only the code under test reads. Those are properties of the APIs
# being imitated, not style choices, so the matching checks are off here.
# pylint: disable=invalid-name,keyword-arg-before-vararg,unused-private-member

from __future__ import annotations

import types
from typing import Any

# The ground-truth QMID used throughout the workspace's local MQ topology,
# trimmed (33 chars) and as the raw 48 byte space padded MQ character field
# the client library actually hands back from MQINQ.
QMID = "AryanMacOSQM1_2026-08-31_09.07.16"
QMID_PADDED = QMID.encode() + b" " * 15

# A NUL padded queue name, as read back from an opened queue's MQOD, and its
# clean form.
QUEUE_NAME = "DEV.QUEUE.1"
QUEUE_NAME_PADDED = QUEUE_NAME.encode() + b"\x00" * 37


class FakeMQMIError(Exception):
    """Stands in for ibmmq's/pymqi's MQMIError: any exception with .reason."""

    def __init__(self, reason: int) -> None:
        self.reason = reason
        super().__init__(f"MQI error, reason {reason}")


class FakeQueueDesc:
    """Stands in for an opened queue's MQOD, as read back after MQOPEN."""

    def __init__(self, object_name: bytes) -> None:
        self.ObjectName = object_name


class FakeGMO:
    """Stands in for an MQGMO. Only the Options bitmask matters here."""

    def __init__(self, options: int = 0) -> None:
        self.Options = options


class FakeCBD:
    """Stands in for an MQCBD. Only CallbackFunction is read/replaced."""

    def __init__(self, callback: Any) -> None:
        self.CallbackFunction = callback


class FakeCBC:
    """Stands in for an MQCBC delivered to a callback at delivery time."""

    def __init__(self, call_type: int, reason: int | None = None) -> None:
        self.CallType = call_type
        self.Reason = reason


def make_cmqc() -> types.SimpleNamespace:
    """Build a fresh CMQC constants namespace."""
    return types.SimpleNamespace(
        MQCA_Q_MGR_IDENTIFIER=2032,
        MQRC_NO_MSG_AVAILABLE=2033,
        MQOP_REGISTER=0x00000100,
        MQCBCT_MSG_REMOVED=6,
        MQCBCT_MSG_NOT_REMOVED=7,
        MQCBCT_START_CALL=1,
        MQGMO_BROWSE_FIRST=0x00000010,
        MQGMO_BROWSE_NEXT=0x00000020,
        MQGMO_BROWSE_MSG_UNDER_CURSOR=0x00000800,
        MQGMO_WAIT=0x00000001,
    )


class FakeQueueManager:
    """Fake QueueManager, the shape shared by both ibmmq and pymqi."""

    def __init__(self) -> None:
        self.connect_calls: list[tuple] = []
        self.put1_calls: list[tuple] = []
        self.inquire_calls = 0
        self.inquire_return: Any = QMID_PADDED
        self.inquire_error: Exception | None = None

    def connect(self, name: str) -> None:
        self.connect_calls.append(("connect", name))

    def connect_with_options(self, name: str, **kwargs: Any) -> None:
        self.connect_calls.append(("connect_with_options", name, kwargs))

    def connect_tcp_client(self, name: str, cd: Any, channel: Any, conn_name: Any) -> None:
        self.connect_calls.append(("connect_tcp_client", name, cd, channel, conn_name))

    def put1(self, q_desc: Any, msg: Any, *opts: Any) -> None:
        self.put1_calls.append((q_desc, msg, opts))

    def inquire(self, selector: int) -> Any:
        self.inquire_calls += 1
        if self.inquire_error is not None:
            raise self.inquire_error
        return self.inquire_return

    def cb(self, **kwargs: Any) -> None:
        pass


class AccessorQueue:
    """ibmmq-flavor Queue double: exposes the public get_name() /
    get_queue_manager() accessors, plus the async cb() registration API.
    """

    def __init__(self, qmgr: Any = None, name: Any = None) -> None:
        self._qmgr = qmgr
        self._name = name
        self.get_return: Any = b"hello"
        self.get_error: Exception | None = None
        self.put_calls: list[tuple] = []
        self.get_calls: list[tuple] = []

    def get_queue_manager(self) -> Any:
        return self._qmgr

    def get_name(self) -> Any:
        return self._name

    def put(self, msg: Any, *opts: Any) -> None:
        self.put_calls.append((msg, opts))

    def get(self, maxLength: Any = None, *opts: Any) -> Any:
        self.get_calls.append((maxLength, opts))
        if self.get_error is not None:
            raise self.get_error
        return self.get_return

    def cb(self, **kwargs: Any) -> None:
        pass


class Queue:
    """pymqi-flavor Queue double: NEITHER get_name() nor
    get_queue_manager() exists, only the name mangled attributes real pymqi
    carries, ``_Queue__qMgr`` and ``_Queue__qDesc``. The class must be
    literally named ``Queue`` for Python's own name mangling to produce
    those exact attribute names.
    """

    def __init__(self, qmgr: Any = None, q_desc: Any = None) -> None:
        self.__qMgr = qmgr
        self.__qDesc = q_desc
        self.get_return: Any = b"hello"
        self.get_error: Exception | None = None
        self.put_calls: list[tuple] = []
        self.get_calls: list[tuple] = []

    def put(self, msg: Any, *opts: Any) -> None:
        self.put_calls.append((msg, opts))

    def get(self, maxLength: Any = None, *opts: Any) -> Any:
        self.get_calls.append((maxLength, opts))
        if self.get_error is not None:
            raise self.get_error
        return self.get_return


def make_client_module(name: str, with_cb: bool) -> types.ModuleType:
    """Build a fresh fake client module, suitable for injection into
    sys.modules, so the instrumentor's own import_module("ibmmq"/"pymqi")
    picks it up.

    Fresh classes every call, so wrapping applied by one test can never
    leak into another test through a shared class object.
    """

    class QueueManager:
        def __init__(self) -> None:
            self.connect_calls: list[tuple] = []
            self.put1_calls: list[tuple] = []
            self.inquire_calls = 0
            self.inquire_return: Any = QMID_PADDED

        def connect(self, name: str) -> None:
            self.connect_calls.append(("connect", name))

        def connect_with_options(self, name: str, **kwargs: Any) -> None:
            self.connect_calls.append(("connect_with_options", name, kwargs))

        def connect_tcp_client(self, name: str, cd: Any, channel: Any, conn_name: Any) -> None:
            self.connect_calls.append(("connect_tcp_client", name, cd, channel, conn_name))

        def put1(self, q_desc: Any, msg: Any, *opts: Any) -> None:
            self.put1_calls.append((q_desc, msg, opts))

        def inquire(self, selector: int) -> Any:
            self.inquire_calls += 1
            return self.inquire_return

    class AccessorQueueDouble:
        def __init__(self, qmgr: Any = None, name: Any = None) -> None:
            self._qmgr = qmgr
            self._name = name
            self.put_calls: list[tuple] = []
            self.get_calls: list[tuple] = []

        def get_queue_manager(self) -> Any:
            return self._qmgr

        def get_name(self) -> Any:
            return self._name

        def put(self, msg: Any, *opts: Any) -> None:
            self.put_calls.append((msg, opts))

        def get(self, maxLength: Any = None, *opts: Any) -> Any:
            self.get_calls.append((maxLength, opts))
            return b"hello"

    if with_cb:

        def _cb(self: Any, **kwargs: Any) -> None:
            pass

        QueueManager.cb = _cb
        AccessorQueueDouble.cb = _cb

    module = types.ModuleType(name)
    module.CMQC = make_cmqc()
    module.QueueManager = QueueManager
    module.Queue = AccessorQueueDouble
    module.MQMIError = FakeMQMIError
    return module
