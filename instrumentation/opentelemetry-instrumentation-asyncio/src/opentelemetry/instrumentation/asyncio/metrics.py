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

ASYNCIO_COROUTINE_DURATION = "asyncio.coroutine.duration"
ASYNCIO_COROUTINE_EXCEPTIONS = "asyncio.coroutine.exceptions"
ASYNCIO_COROUTINE_CANCELLED = "asyncio.coroutine.cancelled"
ASYNCIO_COROUTINE_ACTIVE = "asyncio.coroutine.active"
ASYNCIO_COROUTINE_CREATED = "asyncio.coroutine.created"
ASYNCIO_COROUTINE_FINISHED = "asyncio.coroutine.finished"
ASYNCIO_COROUTINE_TIMEOUTS = "asyncio.coroutine.timeouts"

ASYNCIO_COROUTINE_NAME = "coroutine.name"
ASYNCIO_EXCEPTIONS_NAME = "exceptions.name"

ASYNCIO_FUTURES_DURATION = "asyncio.futures.duration"
ASYNCIO_FUTURES_EXCEPTIONS = "asyncio.futures.exceptions"
ASYNCIO_FUTURES_CANCELLED = "asyncio.futures.cancelled"
ASYNCIO_FUTURES_CREATED = "asyncio.futures.created"
ASYNCIO_FUTURES_ACTIVE = "asyncio.futures.active"
ASYNCIO_FUTURES_FINISHED = "asyncio.futures.finished"
ASYNCIO_FUTURES_TIMEOUTS = "asyncio.futures.timeouts"

ASYNCIO_TO_THREAD_DURATION = "asyncio.to_thread.duration"
ASYNCIO_TO_THREAD_EXCEPTIONS = "asyncio.to_thread.exceptions"
ASYNCIO_TO_THREAD_CREATED = "asyncio.to_thread.created"
ASYNCIO_TO_THREAD_ACTIVE = "asyncio.to_thread.active"
ASYNCIO_TO_THREAD_FINISHED = "asyncio.to_thread.finished"

__all__ = [
    "ASYNCIO_COROUTINE_DURATION",
    "ASYNCIO_COROUTINE_EXCEPTIONS",
    "ASYNCIO_COROUTINE_CANCELLED",
    "ASYNCIO_COROUTINE_ACTIVE",
    "ASYNCIO_COROUTINE_CREATED",
    "ASYNCIO_COROUTINE_FINISHED",
    "ASYNCIO_COROUTINE_TIMEOUTS",

    "ASYNCIO_COROUTINE_NAME",
    "ASYNCIO_EXCEPTIONS_NAME",

    "ASYNCIO_FUTURES_DURATION",
    "ASYNCIO_FUTURES_EXCEPTIONS",
    "ASYNCIO_FUTURES_CANCELLED",
    "ASYNCIO_FUTURES_CREATED",
    "ASYNCIO_FUTURES_ACTIVE",
    "ASYNCIO_FUTURES_FINISHED",
    "ASYNCIO_FUTURES_TIMEOUTS",

    "ASYNCIO_TO_THREAD_DURATION",
    "ASYNCIO_TO_THREAD_EXCEPTIONS",
    "ASYNCIO_TO_THREAD_CREATED",
    "ASYNCIO_TO_THREAD_ACTIVE",
    "ASYNCIO_TO_THREAD_FINISHED",
]
