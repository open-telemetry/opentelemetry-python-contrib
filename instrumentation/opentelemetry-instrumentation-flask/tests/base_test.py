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

from concurrent.futures import ThreadPoolExecutor, as_completed
from random import randint

import flask
from werkzeug.test import Client
from werkzeug.wrappers import Response

from opentelemetry import context, trace


class InstrumentationTest:
    @staticmethod
    def _hello_endpoint(helloid):
        if helloid == 500:
            raise ValueError(":-(")
        return "Hello: " + str(helloid)

    @staticmethod
    def _sqlcommenter_endpoint():
        current_context = context.get_current()
        sqlcommenter_flask_values = current_context.get(
            "SQLCOMMENTER_ORM_TAGS_AND_VALUES", {}
        )
        return sqlcommenter_flask_values

    @staticmethod
    def _copy_context_endpoint():
        @flask.copy_current_request_context
        def _extract_header():
            return flask.request.headers["x-req"]

        # Despite `_extract_header` copying the request context,
        # calling it shouldn't detach the parent Flask span's contextvar
        request_header = _extract_header()

        return {
            "span_name": trace.get_current_span().name,
            "request_header": request_header,
        }

    @staticmethod
    def _multithreaded_endpoint(count):
        def do_random_stuff():
            @flask.copy_current_request_context
            def inner():
                return randint(0, 100)

            return inner

        executor = ThreadPoolExecutor(count)
        futures = []
        for _ in range(count):
            futures.append(executor.submit(do_random_stuff()))
        numbers = []
        for future in as_completed(futures):
            numbers.append(future.result())

        return " ".join([str(i) for i in numbers])

    @staticmethod
    def _custom_response_headers():
        resp = flask.Response("test response")
        resp.headers["content-type"] = "text/plain; charset=utf-8"
        resp.headers["content-length"] = "13"
        resp.headers[
            "my-custom-header"
        ] = "my-custom-value-1,my-custom-header-2"
        resp.headers[
            "my-custom-regex-header-1"
        ] = "my-custom-regex-value-1,my-custom-regex-value-2"
        resp.headers[
            "My-Custom-Regex-Header-2"
        ] = "my-custom-regex-value-3,my-custom-regex-value-4"
        resp.headers["my-secret-header"] = "my-secret-value"
        return resp

    def _common_initialization(self):
        def excluded_endpoint():
            return "excluded"

        def excluded2_endpoint():
            return "excluded2"

        # pylint: disable=no-member
        self.app.route("/hello/<int:helloid>")(self._hello_endpoint)
        self.app.route("/sqlcommenter")(self._sqlcommenter_endpoint)
        self.app.route("/multithreaded")(self._multithreaded_endpoint)
        self.app.route("/copy_context")(self._copy_context_endpoint)
        self.app.route("/excluded/<int:helloid>")(self._hello_endpoint)
        self.app.route("/excluded")(excluded_endpoint)
        self.app.route("/excluded2")(excluded2_endpoint)
        self.app.route("/test_custom_response_headers")(
            self._custom_response_headers
        )

        # pylint: disable=attribute-defined-outside-init
        self.client = Client(self.app, Response)
