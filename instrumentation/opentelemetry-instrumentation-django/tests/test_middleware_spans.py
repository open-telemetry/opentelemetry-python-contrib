# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from sys import modules
from unittest.mock import patch

from django import VERSION
from django.conf import settings
from django.http import HttpResponse
from django.test.client import Client
from django.test.utils import setup_test_environment, teardown_test_environment
from django.utils.deprecation import MiddlewareMixin

from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.instrumentation.django import DjangoInstrumentor
from opentelemetry.test.wsgitestutil import WsgiTestBase
from opentelemetry.trace import SpanKind

DJANGO_2_0 = VERSION >= (2, 0)

if DJANGO_2_0:
    from django.urls import re_path
else:
    from django.conf.urls import url as re_path


def traced_view(request):
    return HttpResponse()


class MixinMiddleware(MiddlewareMixin):
    def process_request(self, request):
        pass


class NewStyleMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)


def function_middleware(get_response):
    def middleware(request):
        return get_response(request)

    return middleware


class ErrorMiddleware(MiddlewareMixin):
    def process_request(self, request):
        raise RuntimeError("middleware error")


urlpatterns = [
    re_path(r"^traced/", traced_view),
]

_django_instrumentor = DjangoInstrumentor()
_THIS_MODULE = modules[__name__].__name__

_TEST_MIDDLEWARE = [
    f"{_THIS_MODULE}.MixinMiddleware",
    f"{_THIS_MODULE}.NewStyleMiddleware",
    f"{_THIS_MODULE}.function_middleware",
]


class TestMiddlewareSpans(WsgiTestBase):
    @classmethod
    def setUpClass(cls):
        if not settings.configured:
            settings.configure(ROOT_URLCONF=modules[__name__])
        super().setUpClass()

    def setUp(self):
        super().setUp()
        setup_test_environment()
        middleware = getattr(settings, "MIDDLEWARE", [])
        self._original_middleware = list(middleware)
        self._original_root_urlconf = getattr(settings, "ROOT_URLCONF", None)
        middleware.clear()
        middleware.extend(_TEST_MIDDLEWARE)
        settings.ROOT_URLCONF = modules[__name__]
        self.env_patch = patch.dict(
            "os.environ",
            {OTEL_SEMCONV_STABILITY_OPT_IN: "default"},
        )
        _OpenTelemetrySemanticConventionStability._initialized = False
        self.env_patch.start()
        _django_instrumentor.instrument(is_middleware_spans_enabled=True)

    def tearDown(self):
        super().tearDown()
        self.env_patch.stop()
        teardown_test_environment()
        _django_instrumentor.uninstrument()
        middleware = getattr(settings, "MIDDLEWARE", [])
        middleware.clear()
        middleware.extend(self._original_middleware)
        if self._original_root_urlconf is not None:
            settings.ROOT_URLCONF = self._original_root_urlconf

    def _get_spans_by_kind(self):
        spans = self.memory_exporter.get_finished_spans()
        server_spans = [s for s in spans if s.kind == SpanKind.SERVER]
        mw_spans = [s for s in spans if s.kind == SpanKind.INTERNAL]
        return server_spans, mw_spans

    def test_all_categories_create_spans(self):
        Client().get("/traced/")
        server_spans, mw_spans = self._get_spans_by_kind()

        self.assertEqual(len(server_spans), 1)
        self.assertEqual(len(mw_spans), 3)

        mw_names = {s.name for s in mw_spans}
        self.assertIn("django.middleware MixinMiddleware", mw_names)
        self.assertIn("django.middleware NewStyleMiddleware", mw_names)
        self.assertIn("django.middleware function_middleware", mw_names)

    def test_mixin_middleware_creates_span(self):
        Client().get("/traced/")
        _, mw_spans = self._get_spans_by_kind()

        mixin_spans = [
            s
            for s in mw_spans
            if s.name == "django.middleware MixinMiddleware"
        ]
        self.assertEqual(len(mixin_spans), 1)

    def test_newstyle_middleware_creates_span(self):
        Client().get("/traced/")
        _, mw_spans = self._get_spans_by_kind()

        newstyle_spans = [
            s
            for s in mw_spans
            if s.name == "django.middleware NewStyleMiddleware"
        ]
        self.assertEqual(len(newstyle_spans), 1)

    def test_function_middleware_creates_span(self):
        Client().get("/traced/")
        _, mw_spans = self._get_spans_by_kind()

        func_spans = [
            s
            for s in mw_spans
            if s.name == "django.middleware function_middleware"
        ]
        self.assertEqual(len(func_spans), 1)

    # Span properties

    def test_span_kind_is_internal(self):
        Client().get("/traced/")
        _, mw_spans = self._get_spans_by_kind()

        for span in mw_spans:
            self.assertEqual(span.kind, SpanKind.INTERNAL)

    def test_spans_share_trace_with_server_span(self):
        Client().get("/traced/")
        server_spans, mw_spans = self._get_spans_by_kind()

        self.assertEqual(len(server_spans), 1)
        server_trace_id = server_spans[0].get_span_context().trace_id

        for mw_span in mw_spans:
            self.assertEqual(
                mw_span.get_span_context().trace_id,
                server_trace_id,
            )

    def test_span_naming_format(self):
        Client().get("/traced/")
        _, mw_spans = self._get_spans_by_kind()

        for span in mw_spans:
            self.assertTrue(
                span.name.startswith("django.middleware "),
                f"Span name '{span.name}' does not match expected format",
            )

    # Edge cases

    def test_disabled_by_default(self):
        _django_instrumentor.uninstrument()
        _django_instrumentor.instrument()

        Client().get("/traced/")
        _, mw_spans = self._get_spans_by_kind()
        self.assertEqual(len(mw_spans), 0)

    def test_uninstrument_removes_spans(self):
        _django_instrumentor.uninstrument()
        _django_instrumentor.instrument()

        Client().get("/traced/")
        _, mw_spans = self._get_spans_by_kind()
        self.assertEqual(len(mw_spans), 0)

    def _reinstrument_with_middleware(self, middleware_list, **kwargs):
        _django_instrumentor.uninstrument()
        middleware = getattr(settings, "MIDDLEWARE", [])
        middleware.clear()
        middleware.extend(middleware_list)
        kwargs.setdefault("is_middleware_spans_enabled", True)
        _django_instrumentor.instrument(**kwargs)

    def test_middleware_error_creates_span(self):
        self._reinstrument_with_middleware([f"{_THIS_MODULE}.ErrorMiddleware"])

        try:
            Client().get("/traced/")
        except RuntimeError:
            pass

        spans = self.memory_exporter.get_finished_spans()
        mw_spans = [s for s in spans if s.kind == SpanKind.INTERNAL]
        self.assertEqual(len(mw_spans), 1)
        self.assertEqual(mw_spans[0].name, "django.middleware ErrorMiddleware")

    def test_respects_middleware_position(self):
        self._reinstrument_with_middleware(
            [
                f"{_THIS_MODULE}.MixinMiddleware",
                f"{_THIS_MODULE}.NewStyleMiddleware",
            ],
            middleware_position=1,
        )

        Client().get("/traced/")
        spans = self.memory_exporter.get_finished_spans()
        mw_spans = [s for s in spans if s.kind == SpanKind.INTERNAL]

        mw_names = {s.name for s in mw_spans}
        self.assertNotIn("django.middleware MixinMiddleware", mw_names)
        self.assertIn("django.middleware NewStyleMiddleware", mw_names)
