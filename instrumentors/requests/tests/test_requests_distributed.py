from requests_mock import Adapter

from ddtrace import config

import typing
import requests_mock

#from ...base import BaseTracerTestCase
from .test_requests import BaseRequestTestCase


from opentelemetry import propagators
from opentelemetry.trace.propagation.httptextformat import (
    Getter,
    HTTPTextFormat,
    HTTPTextFormatT,
    Setter,
)
from opentelemetry.trace.propagation import (
    get_span_from_context,
    set_span_in_context,
)
from opentelemetry.context import Context


# TODO(Mauricio): move to external common utils library
class MockHTTPTextFormat(HTTPTextFormat):
    """Mock propagator for testing purposes."""

    TRACE_ID_KEY = "mock-traceid"
    SPAN_ID_KEY = "mock-spanid"

    def extract(
        self,
        get_from_carrier: Getter[HTTPTextFormatT],
        carrier: HTTPTextFormatT,
        context: typing.Optional[Context] = None,
    ) -> Context:
        trace_id_list = get_from_carrier(carrier, self.TRACE_ID_KEY)
        span_id_list = get_from_carrier(carrier, self.SPAN_ID_KEY)

        if not trace_id_list or not span_id_list:
            return set_span_in_context(trace.INVALID_SPAN)

        return set_span_in_context(
            trace.DefaultSpan(
                trace.SpanContext(
                    trace_id=int(trace_id_list[0]),
                    span_id=int(span_id_list[0]),
                    is_remote=True,
                )
            )
        )

    def inject(
        self,
        set_in_carrier: Setter[HTTPTextFormatT],
        carrier: HTTPTextFormatT,
        context: typing.Optional[Context] = None,
    ) -> None:
        span = get_span_from_context(context)
        set_in_carrier(
            carrier, self.TRACE_ID_KEY, str(span.get_context().trace_id)
        )
        set_in_carrier(
            carrier, self.SPAN_ID_KEY, str(span.get_context().span_id)
        )

class TestRequestsDistributed(BaseRequestTestCase):
    @classmethod
    def setUpClass(cls):
        # Save current propagator to be restored on teardown.
        cls._previous_propagator = propagators.get_global_httptextformat()

        # Set mock propagator for testing.
        propagators.set_global_httptextformat(MockHTTPTextFormat())

    @classmethod
    def tearDownClass(cls):
        # Restore previous propagator.
        propagators.set_global_httptextformat(cls._previous_propagator)
    def headers_here(self, tracer, request, root_span):
        headers = request.headers
        self.assertIn(MockHTTPTextFormat.TRACE_ID_KEY, headers)
        self.assertIn(MockHTTPTextFormat.SPAN_ID_KEY, headers)

        self.assertEqual(
            str(root_span.get_context().trace_id),
            headers[MockHTTPTextFormat.TRACE_ID_KEY],
        )

        req_span = self.tracer.get_current_span()

        self.assertEqual(
            str(req_span.get_context().span_id),
            headers[MockHTTPTextFormat.SPAN_ID_KEY],
        )
        return True

    def headers_not_here(self, tracer, request):
        headers = request.headers
        self.assertNotIn(MockHTTPTextFormat.TRACE_ID_KEY, headers)
        self.assertNotIn(MockHTTPTextFormat.SPAN_ID_KEY, headers)
        return True

    def test_propagation_default(self):
        # ensure by default, distributed tracing is enabled
        adapter = Adapter()
        self.session.mount('mock', adapter)

        with self.tracer.start_as_current_span('root') as root:
            def matcher(request):
                return self.headers_here(self.tracer, request, root)
            adapter.register_uri('GET', 'mock://datadog/foo', additional_matcher=matcher, text='bar')
            resp = self.session.get('mock://datadog/foo')
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.text, 'bar')

    def test_propagation_true_global(self):
        # distributed tracing can be enabled globally
        adapter = Adapter()
        self.session.mount('mock', adapter)

        with self.override_config('requests', dict(distributed_tracing=True)):
            with self.tracer.start_as_current_span('root') as root:
                def matcher(request):
                    return self.headers_here(self.tracer, request, root)
                adapter.register_uri('GET', 'mock://datadog/foo', additional_matcher=matcher, text='bar')
                resp = self.session.get('mock://datadog/foo')
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(resp.text, 'bar')

    def test_propagation_false_global(self):
        # distributed tracing can be disabled globally
        adapter = Adapter()
        self.session.mount('mock', adapter)

        with self.override_config('requests', dict(distributed_tracing=False)):
            with self.tracer.start_as_current_span('root'):
                def matcher(request):
                    return self.headers_not_here(self.tracer, request)
                adapter.register_uri('GET', 'mock://datadog/foo', additional_matcher=matcher, text='bar')
                resp = self.session.get('mock://datadog/foo')
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(resp.text, 'bar')

    def test_propagation_true(self):
        # ensure distributed tracing can be enabled manually
        cfg = config.get_from(self.session)
        cfg['distributed_tracing'] = True
        adapter = Adapter()
        self.session.mount('mock', adapter)

        with self.tracer.start_as_current_span('root') as root:
            def matcher(request):
                return self.headers_here(self.tracer, request, root)
            adapter.register_uri('GET', 'mock://datadog/foo', additional_matcher=matcher, text='bar')
            resp = self.session.get('mock://datadog/foo')
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.text, 'bar')

    def test_propagation_false(self):
        # ensure distributed tracing can be disabled manually
        cfg = config.get_from(self.session)
        cfg['distributed_tracing'] = False
        adapter = Adapter()
        self.session.mount('mock', adapter)

        with self.tracer.start_as_current_span('root'):
            def matcher(request):
                return self.headers_not_here(self.tracer, request)
            adapter.register_uri('GET', 'mock://datadog/foo', additional_matcher=matcher, text='bar')
            resp = self.session.get('mock://datadog/foo')
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.text, 'bar')
