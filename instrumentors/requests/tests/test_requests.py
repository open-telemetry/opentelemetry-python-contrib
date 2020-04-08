import unittest

import contextlib
import requests
from requests import Session
from requests.exceptions import InvalidURL, ConnectionError

import ddtrace

from ddtrace import config
from ddtrace import Pin
from ddtrace.constants import ANALYTICS_SAMPLE_RATE_KEY
from ddtrace.ext import errors, http

from opentelemetry.ext.requests import patch, unpatch

from opentelemetry import trace as trace_api
from opentelemetry.sdk import trace
from opentelemetry.sdk.trace import export
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

#from ...base import BaseTracerTestCase
#from ...util import override_global_tracer
#from ...utils import assert_span_http_status_code

# socket name comes from https://english.stackexchange.com/a/44048
SOCKET = 'httpbin.org'
URL_200 = 'http://{}/status/200'.format(SOCKET)
URL_500 = 'http://{}/status/500'.format(SOCKET)


class BaseRequestTestCase(unittest.TestCase):
    """Create a traced Session, patching during the setUp and
    unpatching after the tearDown
    """
    def setUp(self):
        patch()
        self.session = Session()

        tracer_provider = trace.TracerProvider()
        self.tracer = tracer_provider.get_tracer(__name__)
        trace_api.set_tracer_provider(tracer_provider)
        self.memory_exporter = InMemorySpanExporter()
        span_processor = export.SimpleExportSpanProcessor(self.memory_exporter)
        tracer_provider.add_span_processor(span_processor)

    def tearDown(self):
        unpatch()

    @staticmethod
    @contextlib.contextmanager
    def override_config(integration, values):
        """
        Temporarily override an integration configuration value::
            >>> with self.override_config('flask', dict(service_name='test-service')):
                # Your test
        """
        options = getattr(ddtrace.config, integration)

        original = dict(
            (key, options.get(key))
            for key in values.keys()
        )

        options.update(values)
        try:
            yield
        finally:
            options.update(original)


class TestRequests(BaseRequestTestCase):
    def test_resource_path(self):
        out = self.session.get(URL_200)
        self.assertEqual(out.status_code, 200)
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        s = spans[0]
        self.assertEqual(s.attributes["http.url"], URL_200)

    def test_args_kwargs(self):
        # ensure all valid combinations of args / kwargs work
        url = URL_200
        method = 'GET'
        inputs = [
            ([], {'method': method, 'url': url}),
            ([method], {'url': url}),
            ([method, url], {}),
        ]

        for args, kwargs in inputs:
            # ensure a traced request works with these args
            out = self.session.request(*args, **kwargs)
            self.assertEqual(out.status_code, 200)
            # validation
            spans = self.memory_exporter.get_finished_spans()
            # TODO(Mauricio): clear is needed because the loop
            self.memory_exporter.clear()
            self.assertEqual(len(spans), 1)
            s = spans[0]
            self.assertEqual(s.attributes[http.METHOD], 'GET')
            self.assertEqual(s.attributes[http.STATUS_CODE], 200)

    def test_untraced_request(self):
        # ensure the unpatch removes tracing
        unpatch()
        untraced = Session()

        out = untraced.get(URL_200)
        self.assertEqual(out.status_code, 200)
        # validation
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)

    def test_double_patch(self):
        # ensure that double patch doesn't duplicate instrumentation
        patch()
        session = Session()

        out = session.get(URL_200)
        self.assertEqual(out.status_code, 200)
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

    def test_200(self):
        out = self.session.get(URL_200)
        self.assertEqual(out.status_code, 200)
        # validation
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        s = spans[0]
        self.assertEqual(s.attributes[http.METHOD], 'GET')
        self.assertEqual(s.attributes[http.STATUS_CODE], 200)
        self.assertIs(s.status.canonical_code, trace_api.status.StatusCanonicalCode.OK)
        self.assertEqual(s.kind, trace_api.SpanKind.CLIENT)
        self.assertIsNone(s.attributes.get(http.QUERY_STRING))

    def test_200_send(self):
        # when calling send directly
        req = requests.Request(url=URL_200, method='GET')
        req = self.session.prepare_request(req)

        out = self.session.send(req)
        self.assertEqual(out.status_code, 200)
        # validation
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        s = spans[0]
        self.assertEqual(s.attributes[http.METHOD], 'GET')
        self.assertEqual(s.attributes[http.STATUS_CODE], 200)
        self.assertIs(s.status.canonical_code, trace_api.status.StatusCanonicalCode.OK)
        self.assertEqual(s.kind, trace_api.SpanKind.CLIENT)

    def _test_200_query_string(self):
        # ensure query string is removed before adding url to metadata
        query_string = 'key=value&key2=value2'
        with self.override_http_config('requests', dict(trace_query_string=True)):
            out = self.session.get(URL_200 + '?' + query_string)
        self.assertEqual(out.status_code, 200)
        # validation
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        s = spans[0]
        self.assertEqual(s.attributes[http.METHOD], 'GET')
        self.assertEqual(s.attributes[http.STATUS_CODE], 200)
        assert s.get_tag(http.URL) == URL_200
        self.assertIs(s.status.canonical_code, trace_api.status.StatusCanonicalCode.OK)
        self.assertEqual(s.kind, trace_api.SpanKind.CLIENT)
        assert s.get_tag(http.QUERY_STRING) == query_string

    def test_requests_module_200(self):
        # ensure the requests API is instrumented even without
        # using a `Session` directly

        out = requests.get(URL_200)
        self.assertEqual(out.status_code, 200)
        # validation
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        s = spans[0]
        self.assertEqual(s.attributes[http.METHOD], 'GET')
        self.assertEqual(s.attributes[http.STATUS_CODE], 200)
        self.assertIs(s.status.canonical_code, trace_api.status.StatusCanonicalCode.OK)
        self.assertEqual(s.kind, trace_api.SpanKind.CLIENT)

    def test_post_500(self):
        out = self.session.post(URL_500)
        # validation
        self.assertEqual(out.status_code, 500)
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        s = spans[0]
        self.assertEqual(s.attributes[http.METHOD], 'POST')
        self.assertEqual(s.attributes[http.STATUS_CODE], 500)
        self.assertIsNot(s.status.canonical_code, trace_api.status.StatusCanonicalCode.OK)

    def test_non_existant_url(self):
        with self.assertRaises(ConnectionError):
            self.session.get('http://doesnotexist.google.com')

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        s = spans[0]
        self.assertEqual(s.attributes[http.METHOD], 'GET')
        self.assertIsNot(s.status.canonical_code, trace_api.status.StatusCanonicalCode.OK)

    def test_500(self):
        out = self.session.get(URL_500)
        self.assertEqual(out.status_code, 500)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        s = spans[0]
        self.assertEqual(s.attributes[http.METHOD], 'GET')
        self.assertEqual(s.attributes[http.STATUS_CODE], 500)
        self.assertIsNot(s.status.canonical_code, trace_api.status.StatusCanonicalCode.OK)


    def test_default_service_name(self):
        # ensure a default service name is set
        out = self.session.get(URL_200)
        self.assertEqual(out.status_code, 200)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        s = spans[0]

        self.assertEqual(s.attributes["service"], "requests")

    def test_user_set_service_name(self):
        # ensure a service name set by the user has precedence
        cfg = config.get_from(self.session)
        cfg['service_name'] = 'clients'
        out = self.session.get(URL_200)
        self.assertEqual(out.status_code, 200)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        s = spans[0]

        self.assertEqual(s.attributes["service"], "clients")

    def test_split_by_domain(self):
        # ensure a service name is generated by the domain name
        # of the ongoing call
        cfg = config.get_from(self.session)
        cfg['split_by_domain'] = True
        out = self.session.get(URL_200)
        self.assertEqual(out.status_code, 200)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        s = spans[0]

        self.assertEqual(s.attributes["service"], "httpbin.org")

    def test_split_by_domain_precedence(self):
        # ensure the split by domain has precedence all the time
        cfg = config.get_from(self.session)
        cfg['split_by_domain'] = True
        cfg['service_name'] = 'intake'
        out = self.session.get(URL_200)
        self.assertEqual(out.status_code, 200)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        s = spans[0]

        self.assertEqual(s.attributes["service"], "httpbin.org")

    def test_split_by_domain_wrong(self):
        # ensure the split by domain doesn't crash in case of a wrong URL;
        # in that case, no spans are created
        cfg = config.get_from(self.session)
        cfg['split_by_domain'] = True
        with self.assertRaises(InvalidURL):
            self.session.get('http:/some>thing')

        # We are wrapping `requests.Session.send` and this error gets thrown before that function
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)

    def test_split_by_domain_remove_auth_in_url(self):
        # ensure that auth details are stripped from URL
        cfg = config.get_from(self.session)
        cfg['split_by_domain'] = True
        out = self.session.get('http://user:pass@httpbin.org')
        self.assertEqual(out.status_code, 200)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        s = spans[0]

        self.assertEqual(s.attributes["service"], "httpbin.org")

    def test_split_by_domain_includes_port(self):
        # ensure that port is included if present in URL
        cfg = config.get_from(self.session)
        cfg['split_by_domain'] = True
        out = self.session.get('http://httpbin.org:80')
        self.assertEqual(out.status_code, 200)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        s = spans[0]

        self.assertEqual(s.attributes["service"], "httpbin.org:80")

    def test_split_by_domain_includes_port_path(self):
        # ensure that port is included if present in URL but not path
        cfg = config.get_from(self.session)
        cfg['split_by_domain'] = True
        out = self.session.get('http://httpbin.org:80/anything/v1/foo')
        self.assertEqual(out.status_code, 200)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        s = spans[0]

        self.assertEqual(s.attributes["service"], "httpbin.org:80")

    def _test_request_and_response_headers(self):
        # Disabled when not configured
        self.session.get(URL_200, headers={'my-header': 'my_value'})
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        s = spans[0]
        assert s.get_tag('http.request.headers.my-header') is None
        assert s.get_tag('http.response.headers.access-control-allow-origin') is None

        # Enabled when explicitly configured
        with self.override_config('requests', {}):
            config.requests.http.trace_headers(['my-header', 'access-control-allow-origin'])
            self.session.get(URL_200, headers={'my-header': 'my_value'})
            spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        s = spans[0]
        assert s.get_tag('http.request.headers.my-header') == 'my_value'
        assert s.get_tag('http.response.headers.access-control-allow-origin') == '*'

    def test_analytics_integration_default(self):
        """
        When making a request
            When an integration trace search is enabled and sample rate is set
                We expect the root span to have the appropriate tag
        """
        self.session.get(URL_200)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        s = spans[0]
        self.assertIsNone(s.attributes.get(ANALYTICS_SAMPLE_RATE_KEY))

    def test_analytics_integration_disabled(self):
        """
        When making a request
            When an integration trace search is enabled and sample rate is set
                We expect the root span to have the appropriate tag
        """
        with self.override_config('requests', dict(analytics_enabled=False, analytics_sample_rate=0.5)):
            self.session.get(URL_200)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        s = spans[0]
        self.assertIsNone(s.attributes.get(ANALYTICS_SAMPLE_RATE_KEY))

    def test_analytics_integration_on(self):
        """
        When making a request
            When an integration trace search is enabled and sample rate is set
                We expect the root span to have the appropriate tag
        """
        with self.override_config('requests', dict(analytics_enabled=True, analytics_sample_rate=0.5)):
            self.session.get(URL_200)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        s = spans[0]
        self.assertEqual(s.attributes[ANALYTICS_SAMPLE_RATE_KEY], 0.5)

    def test_analytics_integration_on_using_pin(self):
        """
        When making a request
            When an integration trace search is enabled and sample rate is set
                We expect the root span to have the appropriate tag
        """
        pin = Pin(service=__name__,
                  app='requests',
                  _config={
                      'service_name': __name__,
                      'distributed_tracing': False,
                      'split_by_domain': False,
                      'analytics_enabled': True,
                      'analytics_sample_rate': 0.5,
                  })
        pin.onto(self.session)
        self.session.get(URL_200)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        s = spans[0]
        self.assertEqual(s.attributes[ANALYTICS_SAMPLE_RATE_KEY], 0.5)

    def test_analytics_integration_on_using_pin_default(self):
        """
        When making a request
            When an integration trace search is enabled and sample rate is set
                We expect the root span to have the appropriate tag
        """
        pin = Pin(service=__name__,
                  app='requests',
                  _config={
                      'service_name': __name__,
                      'distributed_tracing': False,
                      'split_by_domain': False,
                      'analytics_enabled': True,
                  })
        pin.onto(self.session)
        self.session.get(URL_200)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        s = spans[0]
        self.assertEqual(s.attributes[ANALYTICS_SAMPLE_RATE_KEY], 1.0)
