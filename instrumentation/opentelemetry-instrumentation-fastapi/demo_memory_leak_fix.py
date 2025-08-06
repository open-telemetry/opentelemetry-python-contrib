#!/usr/bin/env python3
"""
Demo script to demonstrate the memory leak fix in FastAPIInstrumentor.uninstrument_app()

This script shows the problem described in the issue:
- Calling FastAPIInstrumentor.uninstrument_app() doesn't remove the app parameter
  from the _InstrumentedFastAPI._instrumented_fastapi_apps set
- This can lead to memory leaks when instrumenting and uninstrumenting repeatedly

The fix adds code to remove the app from the set during uninstrument_app().
"""

import sys

import fastapi

from opentelemetry.instrumentation.fastapi import (
    FastAPIInstrumentor,
    _InstrumentedFastAPI,
)


def demonstrate_problem():
    """Demonstrate the memory leak problem"""
    print("=== Demonstrating Memory Leak Problem ===")

    app = fastapi.FastAPI()
    print(f"Initial refcount: {sys.getrefcount(app)}")
    print(
        f"Initial set size: {len(_InstrumentedFastAPI._instrumented_fastapi_apps)}"
    )

    # Instrument the app
    FastAPIInstrumentor.instrument_app(app)
    print(f"After instrument - refcount: {sys.getrefcount(app)}")
    print(
        f"After instrument - set size: {len(_InstrumentedFastAPI._instrumented_fastapi_apps)}"
    )
    print(
        f"App in set: {app in _InstrumentedFastAPI._instrumented_fastapi_apps}"
    )

    # Uninstrument the app (before fix, this wouldn't remove from set)
    FastAPIInstrumentor.uninstrument_app(app)
    print(f"After uninstrument - refcount: {sys.getrefcount(app)}")
    print(
        f"After uninstrument - set size: {len(_InstrumentedFastAPI._instrumented_fastapi_apps)}"
    )
    print(
        f"App in set: {app in _InstrumentedFastAPI._instrumented_fastapi_apps}"
    )

    # With the fix, the app should be removed from the set
    if app not in _InstrumentedFastAPI._instrumented_fastapi_apps:
        print("FIXED: App was properly removed from the set")
    else:
        print("BUG: App is still in the set (memory leak)")


def demonstrate_multiple_cycles():
    """Demonstrate multiple instrument/uninstrument cycles"""
    print("\n=== Multiple Instrument/Uninstrument Cycles ===")

    app = fastapi.FastAPI()
    initial_refcount = sys.getrefcount(app)
    print(f"Initial refcount: {initial_refcount}")

    # Perform multiple cycles
    for cycle_num in range(3):
        FastAPIInstrumentor.instrument_app(app)
        FastAPIInstrumentor.uninstrument_app(app)
        current_refcount = sys.getrefcount(app)
        set_size = len(_InstrumentedFastAPI._instrumented_fastapi_apps)
        print(
            f"Cycle {cycle_num+1}: refcount={current_refcount}, set_size={set_size}"
        )

    final_refcount = sys.getrefcount(app)
    final_set_size = len(_InstrumentedFastAPI._instrumented_fastapi_apps)

    print(f"Final refcount: {final_refcount}")
    print(f"Final set size: {final_set_size}")

    if final_set_size == 0:
        print("FIXED: No memory leak - set is empty")
    else:
        print("BUG: Memory leak - set still contains apps")


def demonstrate_multiple_apps():
    """Demonstrate multiple apps"""
    print("\n=== Multiple Apps Test ===")

    apps = [fastapi.FastAPI() for _ in range(3)]

    print("Instrumenting all apps...")
    for app_idx, app in enumerate(apps):
        FastAPIInstrumentor.instrument_app(app)
        print(f"App {app_idx}: refcount={sys.getrefcount(app)}")

    print(
        f"Set size after instrumenting: {len(_InstrumentedFastAPI._instrumented_fastapi_apps)}"
    )

    print("Uninstrumenting all apps...")
    for app_idx, app in enumerate(apps):
        FastAPIInstrumentor.uninstrument_app(app)
        print(f"App {app_idx}: refcount={sys.getrefcount(app)}")

    final_set_size = len(_InstrumentedFastAPI._instrumented_fastapi_apps)
    print(f"Final set size: {final_set_size}")

    if final_set_size == 0:
        print("FIXED: All apps properly removed from set")
    else:
        print("BUG: Some apps still in set")


if __name__ == "__main__":
    print("FastAPIInstrumentor Memory Leak Fix Demo")
    print("=" * 50)

    demonstrate_problem()
    demonstrate_multiple_cycles()
    demonstrate_multiple_apps()

    print("\n" + "=" * 50)
    print("Summary:")
    print(
        "- The fix adds code to remove apps from _instrumented_fastapi_apps during uninstrument_app()"
    )
    print(
        "- This prevents memory leaks when instrumenting/uninstrumenting repeatedly"
    )
    print(
        "- The fix is backward compatible and doesn't break existing functionality"
    )
