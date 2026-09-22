# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
"""Span logic tests for opentelemetry.instrumentation.ibmmq.utils.

Every wrapper factory in utils.py is called directly here, with the
wrapt calling convention (wrapped, instance, args, kwargs) reproduced by
hand, against the fake ibmmq/pymqi doubles in fakes.py. No sys.modules
injection and no IbmMqInstrumentor involved: this file exercises the span
logic in isolation from the instrumentor wiring, which lives in
test_ibmmq_instrumentation.py.
"""

from __future__ import annotations

import os
from unittest import mock

from opentelemetry.instrumentation.ibmmq import utils
from opentelemetry.instrumentation.utils import suppress_instrumentation
from opentelemetry.semconv._incubating.attributes import messaging_attributes
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind, StatusCode, get_current_span

from . import fakes


def _mock_user_callback() -> mock.MagicMock:
    """A MagicMock standing in for the app's own MQCB callback.

    Needs a spec, otherwise MagicMock auto-creates any attribute accessed
    on it (including the "already wrapped" marker utils.py probes for via
    getattr(..., marker, False)), which would always come back truthy and
    make make_cb_wrapper() think it is looking at its own previously
    wrapped callback.
    """

    def signature(**kwargs: object) -> None:
        pass

    return mock.MagicMock(spec=signature)


class TestUtils(TestBase):
    def setUp(self) -> None:
        super().setUp()
        self.tracer = self.tracer_provider.get_tracer(__name__)
        # utils._experimental_attributes_enabled is read once at instrument()
        # time into module state, never per span, so it never resets itself.
        # Guarantee every test starts from the documented default (off) and
        # never leaks its own env var mutations into the next test.
        utils._experimental_attributes_enabled = False
        # These tests call the wrapper factories directly, bypassing
        # IbmMqInstrumentor._instrument(), which is what normally flips this
        # flag on. Default it on here so cb tests exercise the substituted
        # callback's span behaviour; individual tests may flip it off.
        utils.set_instrumented(True)
        self._env_patcher = mock.patch.dict(os.environ, {}, clear=False)
        self._env_patcher.start()

    def tearDown(self) -> None:
        self._env_patcher.stop()
        utils._experimental_attributes_enabled = False
        utils.set_instrumented(False)
        super().tearDown()

    # -- 6: Queue.put -----------------------------------------------------

    def test_queue_put_produces_producer_span(self) -> None:
        queue = fakes.AccessorQueue(name=fakes.QUEUE_NAME)
        wrapper = utils.make_queue_put_wrapper(self.tracer)

        wrapper(queue.put, queue, (b"hello",), {})

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.name, "DEV.QUEUE.1 publish")
        self.assertEqual(span.kind, SpanKind.PRODUCER)
        self.assertEqual(span.attributes[messaging_attributes.MESSAGING_SYSTEM], "ibm.mq")
        self.assertEqual(span.attributes[messaging_attributes.MESSAGING_OPERATION], "publish")
        self.assertEqual(
            span.attributes[messaging_attributes.MESSAGING_DESTINATION_NAME],
            fakes.QUEUE_NAME,
        )
        self.assertEqual(queue.put_calls, [(b"hello", ())])

    # -- 7: QueueManager.put1, three destination forms --------------------

    def test_put1_resolves_destination_for_str_bytes_and_object_forms(self) -> None:
        qmgr = fakes.FakeQueueManager()
        wrapper = utils.make_put1_wrapper(self.tracer)

        wrapper(qmgr.put1, qmgr, (fakes.QUEUE_NAME, b"m1"), {})
        wrapper(qmgr.put1, qmgr, (fakes.QUEUE_NAME_PADDED, b"m2"), {})
        wrapper(qmgr.put1, qmgr, (fakes.FakeQueueDesc(fakes.QUEUE_NAME_PADDED), b"m3"), {})

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 3)
        for span in spans:
            self.assertEqual(span.kind, SpanKind.PRODUCER)
            self.assertEqual(
                span.attributes[messaging_attributes.MESSAGING_DESTINATION_NAME],
                fakes.QUEUE_NAME,
            )
        self.assertEqual(len(qmgr.put1_calls), 3)

    # -- 8: Queue.get success -----------------------------------------------

    def test_queue_get_success_produces_consumer_span(self) -> None:
        cmqc = fakes.make_cmqc()
        queue = fakes.AccessorQueue(name=fakes.QUEUE_NAME)
        wrapper = utils.make_queue_get_wrapper(self.tracer, cmqc)

        result = wrapper(queue.get, queue, (), {})

        self.assertEqual(result, b"hello")
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.name, "DEV.QUEUE.1 receive")
        self.assertEqual(span.kind, SpanKind.CONSUMER)
        self.assertEqual(span.attributes[messaging_attributes.MESSAGING_OPERATION], "receive")

    # -- 9: Queue.get, MQRC_NO_MSG_AVAILABLE -------------------------------

    def test_queue_get_no_msg_available_produces_no_span_and_reraises(self) -> None:
        cmqc = fakes.make_cmqc()
        queue = fakes.AccessorQueue(name=fakes.QUEUE_NAME)
        queue.get_error = fakes.FakeMQMIError(cmqc.MQRC_NO_MSG_AVAILABLE)
        wrapper = utils.make_queue_get_wrapper(self.tracer, cmqc)

        with self.assertRaises(fakes.FakeMQMIError):
            wrapper(queue.get, queue, (), {})

        self.assertEqual(len(self.memory_exporter.get_finished_spans()), 0)

    # -- 10: Queue.get, some other MQ reason -------------------------------

    def test_queue_get_other_error_produces_error_span_and_reraises(self) -> None:
        cmqc = fakes.make_cmqc()
        queue = fakes.AccessorQueue(name=fakes.QUEUE_NAME)
        queue.get_error = fakes.FakeMQMIError(2035)
        wrapper = utils.make_queue_get_wrapper(self.tracer, cmqc)

        with self.assertRaises(fakes.FakeMQMIError):
            wrapper(queue.get, queue, (), {})

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.status.status_code, StatusCode.ERROR)
        self.assertTrue(any(event.name == "exception" for event in span.events))

    # -- 11: browse detection -----------------------------------------------

    def test_browse_get_marks_operation_receive_and_gates_browse_attribute(self) -> None:
        cmqc = fakes.make_cmqc()
        queue = fakes.AccessorQueue(name=fakes.QUEUE_NAME)
        gmo = fakes.FakeGMO(options=cmqc.MQGMO_BROWSE_FIRST)
        wrapper = utils.make_queue_get_wrapper(self.tracer, cmqc)

        # flag off (default): browse is still a receive/CONSUMER span, but
        # the experimental attribute must be entirely absent.
        wrapper(queue.get, queue, (None, gmo), {})
        span = self.memory_exporter.get_finished_spans()[0]
        self.assertEqual(span.kind, SpanKind.CONSUMER)
        self.assertEqual(span.attributes[messaging_attributes.MESSAGING_OPERATION], "receive")
        self.assertNotIn(utils._ATTR_BROWSE, span.attributes)

        self.memory_exporter.clear()
        utils._experimental_attributes_enabled = True
        wrapper(queue.get, queue, (None, gmo), {})
        span = self.memory_exporter.get_finished_spans()[0]
        self.assertIs(span.attributes[utils._ATTR_BROWSE], True)

    # -- 12: QMID on producer and consumer spans ---------------------------

    def test_qmid_present_on_producer_and_consumer_spans_when_enabled(self) -> None:
        utils._experimental_attributes_enabled = True
        cmqc = fakes.make_cmqc()
        qmgr = fakes.FakeQueueManager()
        utils.make_connect_wrapper(cmqc)(qmgr.connect_with_options, qmgr, ("QM1",), {})

        queue = fakes.AccessorQueue(qmgr=qmgr, name=fakes.QUEUE_NAME)
        utils.make_queue_put_wrapper(self.tracer)(queue.put, queue, (b"m",), {})
        utils.make_queue_get_wrapper(self.tracer, cmqc)(queue.get, queue, (), {})

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)
        for span in spans:
            qmid = span.attributes[utils._ATTR_QMID]
            self.assertEqual(qmid, fakes.QMID)
            self.assertEqual(len(qmid), 33)

    # -- 13: QMID resolved once per connection, never per message ----------

    def test_qmid_resolved_once_per_connection(self) -> None:
        # QMID is only ever read for the experimental attribute, so the
        # MQINQ resolve itself is gated behind the same flag.
        utils._experimental_attributes_enabled = True
        cmqc = fakes.make_cmqc()
        qmgr = fakes.FakeQueueManager()
        utils.make_connect_wrapper(cmqc)(qmgr.connect_with_options, qmgr, ("QM1",), {})

        queue = fakes.AccessorQueue(qmgr=qmgr, name=fakes.QUEUE_NAME)
        put_wrapper = utils.make_queue_put_wrapper(self.tracer)
        get_wrapper = utils.make_queue_get_wrapper(self.tracer, cmqc)
        for _ in range(5):
            put_wrapper(queue.put, queue, (b"m",), {})
            get_wrapper(queue.get, queue, (), {})

        self.assertEqual(qmgr.inquire_calls, 1)

    # -- 14: QMID gated behind the experimental env var --------------------

    def test_qmid_gated_behind_experimental_env_var(self) -> None:
        cmqc = fakes.make_cmqc()
        cases = (
            (None, False),
            ("true", True),
            ("1", True),
            ("false", False),
            ("0", False),
        )
        for value, expected_present in cases:
            with self.subTest(value=value):
                self.memory_exporter.clear()
                if value is None:
                    os.environ.pop(utils._EXPERIMENTAL_ENV_VAR, None)
                else:
                    os.environ[utils._EXPERIMENTAL_ENV_VAR] = value
                utils.configure_experimental_attributes()

                qmgr = fakes.FakeQueueManager()
                utils.make_connect_wrapper(cmqc)(qmgr.connect_with_options, qmgr, ("QM1",), {})
                queue = fakes.AccessorQueue(qmgr=qmgr, name=fakes.QUEUE_NAME)
                utils.make_queue_put_wrapper(self.tracer)(queue.put, queue, (b"m",), {})

                span = self.memory_exporter.get_finished_spans()[0]
                self.assertEqual(utils._ATTR_QMID in span.attributes, expected_present)

    # -- 15: pymqi path, name mangled attributes ---------------------------

    def test_pymqi_queue_resolves_name_and_qmgr_from_mangled_attributes(self) -> None:
        qmgr = fakes.FakeQueueManager()
        q_desc = fakes.FakeQueueDesc(fakes.QUEUE_NAME_PADDED)
        queue = fakes.Queue(qmgr=qmgr, q_desc=q_desc)
        wrapper = utils.make_queue_put_wrapper(self.tracer)

        wrapper(queue.put, queue, (b"m",), {})

        span = self.memory_exporter.get_finished_spans()[0]
        name = span.attributes[messaging_attributes.MESSAGING_DESTINATION_NAME]
        self.assertEqual(name, "DEV.QUEUE.1")
        self.assertNotIn("\x00", name)

        # Prove the queue manager was found via _Queue__qMgr specifically:
        # the only route QMID can reach this span is through it.
        utils._experimental_attributes_enabled = True
        qmgr._otel_qmid = fakes.QMID
        self.memory_exporter.clear()
        wrapper(queue.put, queue, (b"m",), {})
        span = self.memory_exporter.get_finished_spans()[0]
        self.assertEqual(span.attributes[utils._ATTR_QMID], fakes.QMID)

    # -- 16: pymqi queue constructed but never opened -----------------------

    def test_pymqi_queue_never_opened_has_no_destination(self) -> None:
        qmgr = fakes.FakeQueueManager()
        queue = fakes.Queue(qmgr=qmgr)  # q_desc left at its None default
        wrapper = utils.make_queue_put_wrapper(self.tracer)

        wrapper(queue.put, queue, (b"m",), {})  # must not raise

        span = self.memory_exporter.get_finished_spans()[0]
        self.assertEqual(span.name, "publish")
        self.assertNotIn(messaging_attributes.MESSAGING_DESTINATION_NAME, span.attributes)

    # -- 17: async MQCB path (ibmmq only) -----------------------------------

    def test_cb_wraps_and_only_spans_message_delivery(self) -> None:
        cmqc = fakes.make_cmqc()
        queue = fakes.AccessorQueue(name=fakes.QUEUE_NAME)
        qmgr = fakes.FakeQueueManager()
        original_callback = _mock_user_callback()
        cbd = fakes.FakeCBD(original_callback)
        cb_wrapper = utils.make_cb_wrapper(self.tracer, cmqc)

        cb_wrapper(queue.cb, queue, (), {"operation": cmqc.MQOP_REGISTER, "cbd": cbd})
        traced_callback = cbd.CallbackFunction
        self.assertIsNot(traced_callback, original_callback)

        md, gmo, msg = mock.MagicMock(), mock.MagicMock(), mock.MagicMock()

        # A real message delivery: one CONSUMER span, callback called through.
        cbc = fakes.FakeCBC(cmqc.MQCBCT_MSG_REMOVED)
        traced_callback(queue_manager=qmgr, queue=queue, md=md, gmo=gmo, msg=msg, cbc=cbc)
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].kind, SpanKind.CONSUMER)
        original_callback.assert_called_once_with(queue_manager=qmgr, queue=queue, md=md, gmo=gmo, msg=msg, cbc=cbc)

        self.memory_exporter.clear()
        original_callback.reset_mock()

        # A non-message MQCB call type (e.g. START_CALL): no span, callback
        # is still called through unconditionally.
        start_cbc = fakes.FakeCBC(cmqc.MQCBCT_START_CALL)
        traced_callback(queue_manager=qmgr, queue=queue, md=md, gmo=gmo, msg=msg, cbc=start_cbc)
        self.assertEqual(len(self.memory_exporter.get_finished_spans()), 0)
        original_callback.assert_called_once_with(
            queue_manager=qmgr, queue=queue, md=md, gmo=gmo, msg=msg, cbc=start_cbc
        )

        self.memory_exporter.clear()
        original_callback.reset_mock()

        # MSG_REMOVED but a wait expiring with no message: no span either.
        no_msg_cbc = fakes.FakeCBC(cmqc.MQCBCT_MSG_REMOVED, reason=cmqc.MQRC_NO_MSG_AVAILABLE)
        traced_callback(queue_manager=qmgr, queue=queue, md=md, gmo=gmo, msg=msg, cbc=no_msg_cbc)
        self.assertEqual(len(self.memory_exporter.get_finished_spans()), 0)
        original_callback.assert_called_once_with(
            queue_manager=qmgr, queue=queue, md=md, gmo=gmo, msg=msg, cbc=no_msg_cbc
        )

    # -- 18: re-registering the same cbd must not double wrap ---------------

    def test_cb_reregistration_of_same_cbd_does_not_double_wrap(self) -> None:
        cmqc = fakes.make_cmqc()
        queue = fakes.AccessorQueue(name=fakes.QUEUE_NAME)
        qmgr = fakes.FakeQueueManager()
        original_callback = _mock_user_callback()
        cbd = fakes.FakeCBD(original_callback)
        cb_wrapper = utils.make_cb_wrapper(self.tracer, cmqc)

        cb_wrapper(queue.cb, queue, (), {"operation": cmqc.MQOP_REGISTER, "cbd": cbd})
        cb_wrapper(queue.cb, queue, (), {"operation": cmqc.MQOP_REGISTER, "cbd": cbd})

        cbc = fakes.FakeCBC(cmqc.MQCBCT_MSG_REMOVED)
        cbd.CallbackFunction(queue_manager=qmgr, queue=queue, md=None, gmo=None, msg=None, cbc=cbc)

        self.assertEqual(len(self.memory_exporter.get_finished_spans()), 1)

    # -- 19: suppress_instrumentation() ------------------------------------

    def test_suppressed_instrumentation_produces_no_spans_but_calls_through(self) -> None:
        cmqc = fakes.make_cmqc()
        queue = fakes.AccessorQueue(name=fakes.QUEUE_NAME)
        put_wrapper = utils.make_queue_put_wrapper(self.tracer)
        get_wrapper = utils.make_queue_get_wrapper(self.tracer, cmqc)

        with suppress_instrumentation():
            put_wrapper(queue.put, queue, (b"m",), {})
            get_wrapper(queue.get, queue, (), {})

        self.assertEqual(len(self.memory_exporter.get_finished_spans()), 0)
        self.assertEqual(len(queue.put_calls), 1)
        self.assertEqual(len(queue.get_calls), 1)

    # -- 20: consumer span is current for the duration of the wrapped call --

    def test_queue_get_span_is_current_during_wrapped_call(self) -> None:
        cmqc = fakes.make_cmqc()
        queue = fakes.AccessorQueue(name=fakes.QUEUE_NAME)
        wrapper = utils.make_queue_get_wrapper(self.tracer, cmqc)
        captured: dict = {}

        def spy_get(*args: object, **kwargs: object) -> object:
            # IBM's own ibmmq/mqotel.py reads get_current_span() from inside
            # the real get() call to attach a link, so this must see the
            # consumer span as current, not whatever span was current before.
            current = get_current_span()
            captured["recording"] = current.is_recording()
            captured["span_id"] = current.get_span_context().span_id
            return queue.get(*args, **kwargs)

        result = wrapper(spy_get, queue, (), {})

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertTrue(captured["recording"])
        self.assertEqual(captured["span_id"], spans[0].context.span_id)
        self.assertEqual(result, b"hello")

    # -- 21: browse bits are read before the wrapped call, not after --------

    def test_browse_detection_reads_gmo_before_wrapped_call(self) -> None:
        utils._experimental_attributes_enabled = True
        cmqc = fakes.make_cmqc()
        queue = fakes.AccessorQueue(name=fakes.QUEUE_NAME)
        gmo = fakes.FakeGMO(options=cmqc.MQGMO_BROWSE_FIRST)
        wrapper = utils.make_queue_get_wrapper(self.tracer, cmqc)

        def get_then_clear_options(*args: object, **kwargs: object) -> object:
            result = queue.get(*args, **kwargs)
            # Mirrors both real clients calling get_opts.unpack(rv[2]) after
            # MQGET, which overwrites the caller's MQGMO Options in place.
            gmo.Options = 0
            return result

        wrapper(get_then_clear_options, queue, (None, gmo), {})

        span = self.memory_exporter.get_finished_spans()[0]
        self.assertIs(span.attributes[utils._ATTR_BROWSE], True)
        self.assertEqual(gmo.Options, 0)

    # -- 22: substituted MQCB callback goes quiet after uninstrument --------

    def test_cb_callback_goes_quiet_after_set_instrumented_false(self) -> None:
        cmqc = fakes.make_cmqc()
        queue = fakes.AccessorQueue(name=fakes.QUEUE_NAME)
        qmgr = fakes.FakeQueueManager()
        original_callback = _mock_user_callback()
        cbd = fakes.FakeCBD(original_callback)
        cb_wrapper = utils.make_cb_wrapper(self.tracer, cmqc)

        cb_wrapper(queue.cb, queue, (), {"operation": cmqc.MQOP_REGISTER, "cbd": cbd})
        traced_callback = cbd.CallbackFunction

        # Simulate uninstrument(): the class methods are unwrapped, but this
        # callback stays armed inside the IBM client's own _stashedCBD.
        utils.set_instrumented(False)

        md, gmo, msg = mock.MagicMock(), mock.MagicMock(), mock.MagicMock()
        cbc = fakes.FakeCBC(cmqc.MQCBCT_MSG_REMOVED)
        traced_callback(queue_manager=qmgr, queue=queue, md=md, gmo=gmo, msg=msg, cbc=cbc)

        self.assertEqual(len(self.memory_exporter.get_finished_spans()), 0)
        original_callback.assert_called_once_with(queue_manager=qmgr, queue=queue, md=md, gmo=gmo, msg=msg, cbc=cbc)
