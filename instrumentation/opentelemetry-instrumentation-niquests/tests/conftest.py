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

"""conftest.py – make the ``responses`` library work with Niquests.

The ``responses`` library is designed for ``requests``. Since Niquests is a
drop-in replacement we can redirect the relevant ``sys.modules`` entries so
that ``responses`` patches Niquests adapters instead.

The async extension (``NiquestsMock``) additionally patches
``AsyncHTTPAdapter.send`` so that ``await session.get(...)`` also hits the
mock registry.

See https://niquests.readthedocs.io/en/latest/community/extensions.html#responses
"""

from __future__ import annotations

import typing
from sys import modules
from unittest import mock as std_mock

import niquests
from niquests.packages import urllib3

# responses is tied to Requests
# and Niquests is entirely compatible with it.
# we can fool it without effort.
modules["requests"] = niquests
modules["requests.adapters"] = niquests.adapters
modules["requests.models"] = niquests.models
modules["requests.exceptions"] = niquests.exceptions
modules["requests.packages.urllib3"] = urllib3

# make 'responses' mock both sync and async
# 'Requests' ever only supported sync
# Fortunately interfaces are mirrored in 'Niquests'
import responses  # noqa: E402  pylint: disable=wrong-import-position


class NiquestsMock(responses.RequestsMock):
    """Asynchronous support for responses"""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(
            *args,
            target="niquests.adapters.HTTPAdapter.send",
            **kwargs,
        )

        self._patcher_async = None

    def unbound_on_async_send(self):
        async def send(
            adapter: "niquests.adapters.AsyncHTTPAdapter",
            request: "niquests.PreparedRequest",
            *args: typing.Any,
            **kwargs: typing.Any,
        ) -> "niquests.Response":
            if args:
                try:
                    kwargs["stream"] = args[0]
                    kwargs["timeout"] = args[1]
                    kwargs["verify"] = args[2]
                    kwargs["cert"] = args[3]
                    kwargs["proxies"] = args[4]
                except IndexError:
                    pass

            resp = self._on_request(adapter, request, **kwargs)

            if kwargs.get("stream"):
                return resp

            resp.__class__ = niquests.Response
            return resp

        return send

    def unbound_on_send(self):
        def send(
            adapter: "niquests.adapters.HTTPAdapter",
            request: "niquests.PreparedRequest",
            *args: typing.Any,
            **kwargs: typing.Any,
        ) -> "niquests.Response":
            if args:
                try:
                    kwargs["stream"] = args[0]
                    kwargs["timeout"] = args[1]
                    kwargs["verify"] = args[2]
                    kwargs["cert"] = args[3]
                    kwargs["proxies"] = args[4]
                except IndexError:
                    pass

            return self._on_request(adapter, request, **kwargs)

        return send

    def start(self) -> None:
        if self._patcher:
            return

        self._patcher = std_mock.patch(
            target=self.target, new=self.unbound_on_send()
        )
        self._patcher_async = std_mock.patch(
            target=self.target.replace("HTTPAdapter", "AsyncHTTPAdapter"),
            new=self.unbound_on_async_send(),
        )

        self._patcher.start()
        self._patcher_async.start()

    def stop(self, allow_assert: bool = True) -> None:
        if self._patcher:
            self._patcher.stop()
            self._patcher_async.stop()

            self._patcher = None
            self._patcher_async = None

        if not self.assert_all_requests_are_fired:
            return

        if not allow_assert:
            return

        not_called = [m for m in self.registered() if m.call_count == 0]
        if not_called:
            raise AssertionError(
                f"Not all requests have been executed {[(match.method, match.url) for match in not_called]!r}"
            )


mock = _default_mock = NiquestsMock(assert_all_requests_are_fired=False)

setattr(responses, "mock", mock)
setattr(responses, "_default_mock", _default_mock)

for kw in [
    "activate",
    "add",
    "_add_from_file",
    "add_callback",
    "add_passthru",
    "assert_call_count",
    "calls",
    "delete",
    "DELETE",
    "get",
    "GET",
    "head",
    "HEAD",
    "options",
    "OPTIONS",
    "patch",
    "PATCH",
    "post",
    "POST",
    "put",
    "PUT",
    "registered",
    "remove",
    "replace",
    "reset",
    "response_callback",
    "start",
    "stop",
    "upsert",
]:
    if not hasattr(responses, kw):
        continue
    setattr(responses, kw, getattr(mock, kw))
