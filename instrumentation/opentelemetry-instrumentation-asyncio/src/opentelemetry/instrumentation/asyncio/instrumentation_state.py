"""
Instrumentation State Tracker

This module provides helper functions to safely track whether a coroutine,
Future, or function has already been instrumented by the OpenTelemetry
asyncio instrumentation layer.

Because some Python objects (like coroutines or functions) may not support
adding custom attributes or may not be weak-referenceable, we use a
weak-reference-based dictionary to track instrumented objects safely and
efficiently without causing memory leaks.

If an object cannot be weak-referenced, we skip tracking it to avoid
runtime errors.

Usage:
    if not _is_instrumented(obj):
        _mark_instrumented(obj)
        # instrument the object...
"""

import weakref

# A global dictionary to track whether an object has been instrumented.
# Keys are weak references to avoid preventing garbage collection.
_instrumented_tasks = {}


def _get_weak_key(obj):
    """
    Attempt to create a weak reference key for the given object.

    Some object types (e.g., built-in functions or async_generator_asend)
    do not support weak references. In those cases, return None.

    Args:
        obj: The object to generate a weak reference for.

    Returns:
        A weakref.ref to the object if supported, otherwise None.
    """
    try:
        return weakref.ref(obj)
    except TypeError:
        return None


def _is_instrumented(obj) -> bool:
    """
    Check if the object has already been instrumented.

    Args:
        obj: The coroutine, function, or Future to check.

    Returns:
        True if the object is already marked as instrumented, False otherwise.
    """
    key = _get_weak_key(obj)
    return key in _instrumented_tasks if key else False


def _mark_instrumented(obj):
    """
    Mark the object as instrumented to avoid double-instrumentation.

    Only objects that support weak references are tracked. Unsupported
    objects are silently skipped.

    Args:
        obj: The coroutine, function, or Future to mark.
    """
    key = _get_weak_key(obj)
    if key:
        _instrumented_tasks[key] = True
