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

# This file defines a "RequestMocker" that facilities mocking the "requests"
# API. There are a few reasons that we use this approach to testing:
#
#    1. Security - although "vcrpy" provides a means of filtering data,
#       it can be error-prone; use of this solution risks exposing API keys,
#       auth tokens, etc. It can also inadvertently record fields that are
#       visibility-restricted (such as fields that are returned and available
#       when recording using privileged API keys where such fields would not
#       ordinarily be returned to users with non-privileged API keys).
#
#    2. Reproducibility - although the tests may be reproducible once the
#       recording is present, updating the recording often has external
#       dependencies that may be difficult to reproduce.
#
#    3. Costs - there are both time costs and monetary costs to the external
#       dependencies required for a record/replay solution.
#
# Because they APIs that need to be mocked are simple enough and well documented
# enough, it seems approachable to mock the requests library, instead.

import copy
import functools
import http.client
import io
import json
from typing import Optional

import requests
import requests.sessions


class RequestsCallArgs:
    def __init__(
        self,
        session: requests.sessions.Session,
        request: requests.PreparedRequest,
        **kwargs,
    ):
        self._session = session
        self._request = request
        self._kwargs = kwargs

    @property
    def session(self):
        return self._session

    @property
    def request(self):
        return self._request

    @property
    def kwargs(self):
        return self._kwargs


class RequestsCall:
    def __init__(self, args: RequestsCallArgs, response_generator):
        self._args = args
        self._response_generator = response_generator

    @property
    def args(self):
        return self._args

    @property
    def response(self):
        return self._response_generator(self._args)


def _return_error_status(
    args: RequestsCallArgs, status_code: int, reason: Optional[str] = None
):
    result = requests.Response()
    result.url = args.request.url
    result.status_code = status_code
    result.reason = reason or http.client.responses.get(status_code)
    result.request = args.request
    return result


def _return_404(args: RequestsCallArgs):
    return _return_error_status(args, 404, "Not Found")


def _to_response_generator(response):
    if response is None:
        raise ValueError("response must not be None")
    if isinstance(response, int):
        return lambda args: _return_error_status(args, response)
    if isinstance(response, requests.Response):

        def generate_response_from_response(args):
            new_response = copy.deepcopy(response)
            new_response.request = args.request
            new_response.url = args.request.url
            return new_response

        return generate_response_from_response
    if isinstance(response, dict):

        def generate_response_from_dict(args):
            result = requests.Response()
            result.status_code = 200
            result.headers["content-type"] = "application/json"
            result.encoding = "utf-8"
            result.raw = io.BytesIO(json.dumps(response).encode())
            return result

        return generate_response_from_dict
    raise ValueError(f"Unsupported response type: {type(response)}")


def _to_stream_response_generator(response_generators):
    if len(response_generators) == 1:
        return response_generators[0]

    def combined_generator(args):
        first_response = response_generators[0](args)
        if first_response.status_code != 200:
            return first_response
        result = requests.Response()
        result.status_code = 200
        result.headers["content-type"] = "application/json"
        result.encoding = "utf-8"
        result.headers["transfer-encoding"] = "chunked"
        contents = []
        for generator in response_generators:
            response = generator(args)
            if response.status_code != 200:
                continue
            response_json = response.json()
            response_json_str = json.dumps(response_json)
            contents.append(f"data: {response_json_str}")
        contents_str = "\r\n".join(contents)
        full_contents = f"{contents_str}\r\n\r\n"
        result.raw = io.BytesIO(full_contents.encode())
        return result

    return combined_generator


class RequestsMocker:
    def __init__(self):
        self._original_send = requests.sessions.Session.send
        self._calls = []
        self._handlers = []

    def install(self):
        @functools.wraps(requests.sessions.Session.send)
        def replacement_send(
            s: requests.sessions.Session,
            request: requests.PreparedRequest,
            **kwargs,
        ):
            return self._do_send(s, request, **kwargs)

        requests.sessions.Session.send = replacement_send

    def uninstall(self):
        requests.sessions.Session.send = self._original_send

    def reset(self):
        self._calls = []
        self._handlers = []

    def add_response(self, response, if_matches=None):
        self._handlers.append((if_matches, _to_response_generator(response)))

    @property
    def calls(self):
        return self._calls

    def _do_send(
        self,
        session: requests.sessions.Session,
        request: requests.PreparedRequest,
        **kwargs,
    ):
        stream = kwargs.get("stream", False)
        if not stream:
            return self._do_send_non_streaming(session, request, **kwargs)
        return self._do_send_streaming(session, request, **kwargs)

    def _do_send_streaming(
        self,
        session: requests.sessions.Session,
        request: requests.PreparedRequest,
        **kwargs,
    ):
        args = RequestsCallArgs(session, request, **kwargs)
        response_generators = []
        for matcher, response_generator in self._handlers:
            if matcher is None:
                response_generators.append(response_generator)
            elif matcher(args):
                response_generators.append(response_generator)
        if not response_generators:
            response_generators.append(_return_404)
        response_generator = _to_stream_response_generator(response_generators)
        call = RequestsCall(args, response_generator)
        result = call.response
        self._calls.append(call)
        return result

    def _do_send_non_streaming(
        self,
        session: requests.sessions.Session,
        request: requests.PreparedRequest,
        **kwargs,
    ):
        args = RequestsCallArgs(session, request, **kwargs)
        response_generator = self._lookup_response_generator(args)
        call = RequestsCall(args, response_generator)
        result = call.response
        self._calls.append(call)
        return result

    def _lookup_response_generator(self, args: RequestsCallArgs):
        for matcher, response_generator in self._handlers:
            if matcher is None:
                return response_generator
            if matcher(args):
                return response_generator
        return _return_404
