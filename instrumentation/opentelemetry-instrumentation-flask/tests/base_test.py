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

from werkzeug.test import Client
from werkzeug.wrappers import BaseResponse
from flask import Response

class InstrumentationTest:
    @staticmethod
    def _hello_endpoint(helloid):
        if helloid == 500:
            raise ValueError(":-(")
        return "Hello: " + str(helloid)

    @staticmethod
    def _custom_response_headers():
        resp = Response("test response")
        resp.headers["content-type"] = "text/plain; charset=utf-8"
        resp.headers["content-length"] = "13"
        resp.headers["my-custom-header"] = "my-custom-value-1,my-custom-header-2"
        return resp
    
    def _common_initialization(self):
        def excluded_endpoint():
            return "excluded"

        def excluded2_endpoint():
            return "excluded2"
        
        # pylint: disable=no-member
        self.app.route("/hello/<int:helloid>")(self._hello_endpoint)
        self.app.route("/excluded/<int:helloid>")(self._hello_endpoint)
        self.app.route("/excluded")(excluded_endpoint)
        self.app.route("/excluded2")(excluded2_endpoint)
        self.app.route("/test_custom_response_headers")(self._custom_response_headers)

        # pylint: disable=attribute-defined-outside-init
        self.client = Client(self.app, BaseResponse)
