# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

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
