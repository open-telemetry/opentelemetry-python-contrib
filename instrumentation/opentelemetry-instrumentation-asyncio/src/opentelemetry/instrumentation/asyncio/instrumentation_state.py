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

# A global WeakKeyDictionary to track instrumented objects.
# Entries are automatically removed when the objects are garbage collected.
_instrumented_tasks = weakref.WeakKeyDictionary()


def _is_instrumented(obj) -> bool:
    """
    Check whether the given object has already been marked as instrumented.

    Args:
        obj: A coroutine, function, or Future.

    Returns:
        True if the object has already been marked as instrumented.
        False if it has not, or if it does not support weak references.
    """
    try:
        return _instrumented_tasks.get(obj, False)
    except TypeError:
        # The object does not support weak references.
        return False


def _mark_instrumented(obj):
    """
    Mark the given object as instrumented.

    This function only tracks objects that support weak references.
    Unsupported objects are ignored without raising errors.

    Args:
        obj: A coroutine, function, or Future.
    """
    try:
        _instrumented_tasks[obj] = True
    except TypeError:
        # The object does not support weak references.
        pass
