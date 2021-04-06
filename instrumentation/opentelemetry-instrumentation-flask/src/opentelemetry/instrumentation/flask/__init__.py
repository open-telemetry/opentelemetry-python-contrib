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

# Note: This package is not named "flask" because of
# https://github.com/PyCQA/pylint/issues/2648

"""
This library builds on the OpenTelemetry WSGI middleware to track web requests
in Flask applications. In addition to opentelemetry-util-http, it
supports Flask-specific features such as:

* The Flask url rule pattern is used as the Span name.
* The ``http.route`` Span attribute is set so that one can see which URL rule
  matched a request.

Usage
-----

.. code-block:: python

    from flask import Flask
    from opentelemetry.instrumentation.flask import FlaskInstrumentor

    app = Flask(__name__)

    FlaskInstrumentor().instrument_app(app)

    @app.route("/")
    def hello():
        return "Hello!"

    if __name__ == "__main__":
        app.run(debug=True)

API
---
"""

from logging import getLogger

import flask

import opentelemetry.instrumentation.wsgi as otel_wsgi
from opentelemetry import context, trace
from opentelemetry.instrumentation.flask.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.propagate import extract
from opentelemetry.util._time import _time_ns
from opentelemetry.util.http import get_excluded_urls
from opentelemetry.sdk.trace import Span



_logger = getLogger(__name__)

_ENVIRON_STARTTIME_KEY = "opentelemetry-flask.starttime_key"
_ENVIRON_SPAN_KEY = "opentelemetry-flask.span_key"
_ENVIRON_ACTIVATION_KEY = "opentelemetry-flask.activation_key"
_ENVIRON_TOKEN = "opentelemetry-flask.token"


_excluded_urls = get_excluded_urls("FLASK")

"""FIND REPLACEMENT FOR Callable"""

def get_default_span_name():
    span_name = ""
    try:
        span_name = flask.request.url_rule.rule
    except AttributeError:
        span_name = otel_wsgi.get_default_span_name(flask.request.environ)
    return span_name

def otel_request_hook_default(span, request):
    return "hi"

def otel_response_hook_default(span, request, response):
    return "hey"

def _rewrapped_app(wsgi_app):
    def _wrapped_app(wrapped_app_environ, start_response):
        # We want to measure the time for route matching, etc.
        # In theory, we could start the span here and use
        # update_name later but that API is "highly discouraged" so
        # we better avoid it.
        wrapped_app_environ[_ENVIRON_STARTTIME_KEY] = _time_ns()

        def _start_response(status, response_headers, *args, **kwargs):
            if not _excluded_urls.url_disabled(flask.request.url):
                span = flask.request.environ.get(_ENVIRON_SPAN_KEY)

                if span:
                    otel_wsgi.add_response_attributes(
                        span, status, response_headers
                    )
                    if _InstrumentedFlask.otel_response_hook:
                        _InstrumentedFlask.otel_response_hook(
                        span, flask.request.environ, flask.Response
                    )
                else:
                    _logger.warning(
                        "Flask environ's OpenTelemetry span "
                        "missing at _start_response(%s)",
                        status,
                    )
            

            return start_response(status, response_headers, *args, **kwargs)

        return wsgi_app(wrapped_app_environ, _start_response)

    return _wrapped_app


def _wrapped_before_request(name_callback, otel_request_hook):
    def _before_request():
        if _excluded_urls.url_disabled(flask.request.url):
            return

        flask_request_environ = flask.request.environ
        span_name = name_callback()
        # request_hook = otel_request_hook()
        token = context.attach(
            extract(flask_request_environ, getter=otel_wsgi.wsgi_getter)
        )

        tracer = trace.get_tracer(__name__, __version__)

        span = tracer.start_span(
            span_name,
            # request_hook,
            kind=trace.SpanKind.SERVER,
            start_time=flask_request_environ.get(_ENVIRON_STARTTIME_KEY),
        )
        if span.is_recording():
            attributes = otel_wsgi.collect_request_attributes(
                flask_request_environ
            )
            if flask.request.url_rule:
                # For 404 that result from no route found, etc, we
                # don't have a url_rule.
                attributes["http.route"] = flask.request.url_rule.rule
            for key, value in attributes.items():
                span.set_attribute(key, value)

        activation = trace.use_span(span, end_on_exit=True)
        activation.__enter__()  # pylint: disable=E1101
        flask_request_environ[_ENVIRON_ACTIVATION_KEY] = activation
        flask_request_environ[_ENVIRON_SPAN_KEY] = span
        flask_request_environ[_ENVIRON_TOKEN] = token
        
        if _InstrumentedFlask.otel_request_hook:
            _InstrumentedFlask.otel_request_hook(span, flask_request_environ)

    return _before_request


def _teardown_request(exc):
    # pylint: disable=E1101
    if _excluded_urls.url_disabled(flask.request.url):
        return

    activation = flask.request.environ.get(_ENVIRON_ACTIVATION_KEY)
    if not activation:
        # This request didn't start a span, maybe because it was created in a
        # way that doesn't run `before_request`, like when it is created with
        # `app.test_request_context`.
        return

    if exc is None:
        activation.__exit__(None, None, None)
    else:
        activation.__exit__(
            type(exc), exc, getattr(exc, "__traceback__", None)
        )
    context.detach(flask.request.environ.get(_ENVIRON_TOKEN))


class _InstrumentedFlask(flask.Flask):

    name_callback = get_default_span_name
    otel_request_hook = otel_request_hook_default
    otel_response_hook = otel_response_hook_default

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._original_wsgi_ = self.wsgi_app
        self.wsgi_app = _rewrapped_app(self.wsgi_app)

        _before_request = _wrapped_before_request(
            _InstrumentedFlask.name_callback,
            _InstrumentedFlask.otel_request_hook,
        )
        self._before_request = _before_request
        self.before_request(_before_request)
        self.teardown_request(_teardown_request)


class FlaskInstrumentor(BaseInstrumentor):
    # pylint: disable=protected-access,attribute-defined-outside-init
    """An instrumentor for flask.Flask

    See `BaseInstrumentor`
    """

    """
    THIS SHOULD BE DONE
    """
    def _instrument(self, **kwargs):
        self._original_flask = flask.Flask
        otel_request_hook = kwargs.pop("request_hook", None)
        otel_response_hook = kwargs.pop("response_hook", None)
        name_callback = kwargs.get("name_callback")
        if callable(name_callback):
            _InstrumentedFlask.name_callback = name_callback
        if callable(otel_request_hook):
            _InstrumentedFlask.otel_request_hook = otel_request_hook
        if callable(otel_response_hook):
            _InstrumentedFlask.otel_response_hook = otel_response_hook
        flask.Flask = _InstrumentedFlask

    def instrument_app(
        self, app, name_callback=get_default_span_name, otel_request_hook=otel_request_hook_default
    ):  # pylint: disable=no-self-use
        if not hasattr(app, "_is_instrumented"):
            app._is_instrumented = False

        if not app._is_instrumented:
            app._original_wsgi_app = app.wsgi_app
            app.wsgi_app = _rewrapped_app(app.wsgi_app)

            _before_request = _wrapped_before_request(name_callback, otel_request_hook)
            app._before_request = _before_request
            app.before_request(_before_request)
            app.teardown_request(_teardown_request)
            app._is_instrumented = True
        else:
            _logger.warning(
                "Attempting to instrument Flask app while already instrumented"
            )

    def _uninstrument(self, **kwargs):
        flask.Flask = self._original_flask

    def uninstrument_app(self, app):  # pylint: disable=no-self-use
        if not hasattr(app, "_is_instrumented"):
            app._is_instrumented = False

        if app._is_instrumented:
            app.wsgi_app = app._original_wsgi_app

            # FIXME add support for other Flask blueprints that are not None
            app.before_request_funcs[None].remove(app._before_request)
            app.teardown_request_funcs[None].remove(_teardown_request)
            del app._original_wsgi_app

            app._is_instrumented = False
        else:
            _logger.warning(
                "Attempting to uninstrument Flask "
                "app while already uninstrumented"
            )
