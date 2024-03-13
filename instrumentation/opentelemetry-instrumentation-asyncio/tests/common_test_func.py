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

import asyncio


async def async_func():
    await asyncio.sleep(0.1)


async def factorial(number: int):
    factorial_value = 1
    for value in range(2, number + 1):
        await asyncio.sleep(0)
        factorial_value *= value
    return factorial_value


async def cancellable_coroutine():
    await asyncio.sleep(2)


async def cancellation_coro():
    task = asyncio.create_task(cancellable_coroutine())

    await asyncio.sleep(0.1)
    task.cancel()

    await task


async def cancellation_create_task():
    await asyncio.create_task(cancellation_coro())


async def ensure_future():
    await asyncio.ensure_future(asyncio.sleep(0))
