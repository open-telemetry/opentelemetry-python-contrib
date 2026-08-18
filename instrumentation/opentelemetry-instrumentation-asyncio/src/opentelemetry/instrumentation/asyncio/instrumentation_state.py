# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
Instrumentation State Tracker

This module provides helper functions to safely track whether a coroutine,
Future, or function has already been instrumented by the OpenTelemetry
asyncio instrumentation layer.

Some Python objects (like coroutines or functions) may not support setting
custom attributes or weak references. To avoid memory leaks and runtime
errors, this module uses a WeakKeyDictionary to safely track instrumented
objects.

If an object cannot be weak-referenced, it is silently skipped.

Usage:
    if not _is_instrumented(obj):
        _mark_instrumented(obj)
        # instrument the object...
"""

import weakref
from typing import Any

# A global WeakSet to track instrumented objects.
# Entries are automatically removed when the objects are garbage collected.
_instrumented_tasks = weakref.WeakSet()


def _is_instrumented(obj: Any) -> bool:
    """
    Check whether the object has already been instrumented.
    If not, mark it as instrumented (only if weakref is supported).

    Args:
        obj: A coroutine, function, or Future.

    Returns:
        True if the object was already instrumented.
        False if the object is not trackable (no weakref support), or just marked now.

    Note:
        In Python 3.12+, some internal types like `async_generator_asend`
        raise TypeError when weakref is attempted.
    """
    try:
        if obj in _instrumented_tasks:
            return True
        _instrumented_tasks.add(obj)
        return False
    except TypeError:
        # Object doesn't support weak references → can't track instrumentation
        return False
