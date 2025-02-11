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

import functools
import requests
import requests.sessions
import io
import json


class RequestsCallArgs:

    def __init__(
        self,
        session: requests.sessions.Session,
        request: requests.PreparedRequest,
        **kwargs):
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



def _return_error_status(args: RequestsCallArgs, status_code: int, reason: str):
    result = requests.Response()
    result.url = args.request.url
    result.status_code = status_code
    result.reason = reason
    result.request = args.request
    return result


def _return_404(args: RequestsCallArgs):
    return _return_error_status(args, 404, 'Not Found')


def _to_response_generator(response):
    if response is None:
        raise ValueError('response must not be None')
    if isinstance(response, int):
        return lambda args: _return_error_status(args, response)
    if isinstance(response, requests.Response):
        def response_generator(args):
            new_response = copy.deepcopy(response)
            new_response.request = args.request
            new_response.url = args.request.url
            return new_response
        return response_generator
    if isinstance(response, dict):
        def response_generator(args):
            result = requests.Response()
            result.status_code = 200
            result.headers['content-type'] = 'application/json'
            result.encoding = 'utf-8'
            result.raw = io.BytesIO(json.dumps(response).encode())
            return result
        return response_generator
    raise ValueError(f'Unsupported response type: {type(response)}')


class RequestsMocker:

    def install(self):
        self._original_send = requests.sessions.Session.send
        @functools.wraps(requests.sessions.Session.send)
        def replacement_send(
            s: requests.sessions.Session,
            request: requests.PreparedRequest,
            **kwargs):
            return self._do_send(s, request, **kwargs)
        requests.sessions.Session.send = replacement_send
        self._calls = []
        self._handlers = []

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
        **kwargs):
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

