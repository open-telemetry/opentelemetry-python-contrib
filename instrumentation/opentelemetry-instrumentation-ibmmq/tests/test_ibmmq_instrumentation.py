# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
"""Instrumentor wiring tests for opentelemetry.instrumentation.ibmmq.

Neither the real ibmmq nor the real pymqi package is importable in this
environment (no MQ broker, no native MQI client library), so every test
here injects a fake client module straight into sys.modules before calling
instrument(), scoped to the test with mock.patch.dict so nothing leaks
between tests. skip_dep_check=True is passed to instrument() throughout:
IbmMqInstrumentor.instrumentation_dependencies() checks real installed
package metadata (importlib.metadata.distribution), which the sys.modules
trick does not affect, and in a clean environment matching the stated CI
constraint (neither package's metadata present) the dependency check would
otherwise always report a conflict and silently skip _instrument().
"""

from __future__ import annotations

import sys
from importlib.metadata import PackageNotFoundError
from unittest import mock

import wrapt

from opentelemetry.instrumentation.ibmmq import IbmMqInstrumentor
from opentelemetry.instrumentation.ibmmq.package import (
    _instruments_any,
    _instruments_ibmmq,
    _instruments_pymqi,
)
from opentelemetry.test.test_base import TestBase

from . import fakes


class TestIbmMqInstrumentation(TestBase):
    def setUp(self) -> None:
        super().setUp()
        self.instrumentor = IbmMqInstrumentor()
        if self.instrumentor.is_instrumented_by_opentelemetry:
            self.instrumentor.uninstrument()

    def tearDown(self) -> None:
        if self.instrumentor.is_instrumented_by_opentelemetry:
            self.instrumentor.uninstrument()
        super().tearDown()

    # -- 1: instrument()/uninstrument() restore the originals --------------

    def test_instrument_then_uninstrument_restores_originals(self) -> None:
        module = fakes.make_client_module("ibmmq", with_cb=True)
        qmgr_cls, queue_cls = module.QueueManager, module.Queue
        wrapped_methods = [
            (qmgr_cls, "connect"),
            (qmgr_cls, "connect_with_options"),
            (qmgr_cls, "put1"),
            (qmgr_cls, "cb"),
            (queue_cls, "put"),
            (queue_cls, "get"),
            (queue_cls, "cb"),
        ]
        # connect_tcp_client is deliberately not wrapped: both real clients
        # have it delegate to connect_with_options.
        original_connect_tcp_client = qmgr_cls.connect_tcp_client
        originals = {(cls, name): getattr(cls, name) for cls, name in wrapped_methods}

        with mock.patch.dict(sys.modules, {"ibmmq": module}, clear=False):
            self.instrumentor.instrument(skip_dep_check=True)
            for cls, name in wrapped_methods:
                self.assertIsInstance(getattr(cls, name), wrapt.BoundFunctionWrapper)
            self.assertIs(qmgr_cls.connect_tcp_client, original_connect_tcp_client)

            self.instrumentor.uninstrument()
            for cls, name in wrapped_methods:
                self.assertIs(getattr(cls, name), originals[(cls, name)])

    # -- 2: pymqi only, wraps put/get/put1/connect*, never cb ---------------

    def test_pymqi_only_wraps_expected_methods_and_never_touches_cb(self) -> None:
        module = fakes.make_client_module("pymqi", with_cb=False)
        qmgr_cls, queue_cls = module.QueueManager, module.Queue
        self.assertFalse(hasattr(qmgr_cls, "cb"))
        self.assertFalse(hasattr(queue_cls, "cb"))

        original_connect_tcp_client = qmgr_cls.connect_tcp_client

        with mock.patch.dict(sys.modules, {"pymqi": module}, clear=False):
            self.instrumentor.instrument(skip_dep_check=True)

            for name in (
                "connect",
                "connect_with_options",
                "put1",
            ):
                self.assertIsInstance(getattr(qmgr_cls, name), wrapt.BoundFunctionWrapper)
            for name in ("put", "get"):
                self.assertIsInstance(getattr(queue_cls, name), wrapt.BoundFunctionWrapper)
            # connect_tcp_client is deliberately not wrapped.
            self.assertIs(qmgr_cls.connect_tcp_client, original_connect_tcp_client)

            wrapped_pairs = set(self.instrumentor._wrapped)
            self.assertNotIn((qmgr_cls, "cb"), wrapped_pairs)
            self.assertNotIn((queue_cls, "cb"), wrapped_pairs)
            self.assertNotIn((qmgr_cls, "connect_tcp_client"), wrapped_pairs)
            # Other installed clients (a real pymqi) are wrapped by the same
            # instrument() call, so count only this module's own targets.
            own_pairs = {pair for pair in wrapped_pairs if pair[0] in (qmgr_cls, queue_cls)}
            self.assertEqual(len(own_pairs), 5)

    # -- 3: ibmmq present, also wraps Queue.cb and QueueManager.cb -----------

    def test_ibmmq_present_also_wraps_cb(self) -> None:
        module = fakes.make_client_module("ibmmq", with_cb=True)
        qmgr_cls, queue_cls = module.QueueManager, module.Queue

        with mock.patch.dict(sys.modules, {"ibmmq": module}, clear=False):
            self.instrumentor.instrument(skip_dep_check=True)

            self.assertIsInstance(qmgr_cls.cb, wrapt.BoundFunctionWrapper)
            self.assertIsInstance(queue_cls.cb, wrapt.BoundFunctionWrapper)
            wrapped_pairs = set(self.instrumentor._wrapped)
            self.assertIn((qmgr_cls, "cb"), wrapped_pairs)
            self.assertIn((queue_cls, "cb"), wrapped_pairs)
            self.assertNotIn((qmgr_cls, "connect_tcp_client"), wrapped_pairs)
            # Other installed clients (a real pymqi) are wrapped by the same
            # instrument() call, so count only this module's own targets.
            own_pairs = {pair for pair in wrapped_pairs if pair[0] in (qmgr_cls, queue_cls)}
            self.assertEqual(len(own_pairs), 7)

    # -- 4: instrumentation_dependencies() resolution order -----------------

    def test_instrumentation_dependencies_resolution_order(self) -> None:
        def only_ibmmq(name: str) -> mock.MagicMock:
            if name == "ibmmq":
                return mock.MagicMock()
            raise PackageNotFoundError(name)

        with mock.patch("opentelemetry.instrumentation.ibmmq.distribution", side_effect=only_ibmmq):
            self.assertEqual(self.instrumentor.instrumentation_dependencies(), (_instruments_ibmmq,))

        def only_pymqi(name: str) -> mock.MagicMock:
            if name == "pymqi":
                return mock.MagicMock()
            raise PackageNotFoundError(name)

        with mock.patch("opentelemetry.instrumentation.ibmmq.distribution", side_effect=only_pymqi):
            self.assertEqual(self.instrumentor.instrumentation_dependencies(), (_instruments_pymqi,))

        def neither(name: str) -> mock.MagicMock:
            raise PackageNotFoundError(name)

        with mock.patch("opentelemetry.instrumentation.ibmmq.distribution", side_effect=neither):
            self.assertEqual(self.instrumentor.instrumentation_dependencies(), _instruments_any)

    # -- 5: double instrument()/uninstrument() are safe ----------------------

    def test_double_instrument_and_uninstrument_never_instrumented_are_safe(self) -> None:
        module = fakes.make_client_module("pymqi", with_cb=False)

        with mock.patch.dict(sys.modules, {"pymqi": module}, clear=False):
            # uninstrument() before ever having instrumented must not raise.
            self.instrumentor.uninstrument()

            self.instrumentor.instrument(skip_dep_check=True)
            wrapped_after_first = list(self.instrumentor._wrapped)

            # BaseInstrumentor guards a second instrument(): no re-wrap.
            self.instrumentor.instrument(skip_dep_check=True)
            self.assertEqual(self.instrumentor._wrapped, wrapped_after_first)

            self.instrumentor.uninstrument()
            # uninstrument() a second time, already uninstrumented, must not raise.
            self.instrumentor.uninstrument()
