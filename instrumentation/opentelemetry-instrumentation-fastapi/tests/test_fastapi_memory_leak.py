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

import sys
import unittest

import fastapi

from opentelemetry.instrumentation.fastapi import (
    FastAPIInstrumentor,
    _InstrumentedFastAPI,
)

# Check if sys.getrefcount is available (not available in PyPy)
HAS_GETREFCOUNT = hasattr(sys, "getrefcount")


class TestFastAPIMemoryLeak(unittest.TestCase):
    """Test for memory leak in FastAPIInstrumentor.uninstrument_app()"""

    def test_refcount_after_uninstrument(self):
        """Test that refcount is restored after uninstrument_app()"""
        if not HAS_GETREFCOUNT:
            self.skipTest(
                "sys.getrefcount not available in this Python implementation"
            )

        app = fastapi.FastAPI()

        # Instrument the app
        FastAPIInstrumentor.instrument_app(app)
        refcount_after_instrument = sys.getrefcount(app)

        # Uninstrument the app
        FastAPIInstrumentor.uninstrument_app(app)
        refcount_after_uninstrument = sys.getrefcount(app)

        # The refcount should be reduced after uninstrument (may not be exactly initial due to Python internals)
        self.assertLess(
            refcount_after_uninstrument,
            refcount_after_instrument,
            "Refcount should be reduced after uninstrument_app()",
        )

        # Verify that the app was removed from the set
        self.assertNotIn(
            app,
            _InstrumentedFastAPI._instrumented_fastapi_apps,
            "App should be removed from _instrumented_fastapi_apps after uninstrument_app()",
        )

    def test_multiple_instrument_uninstrument_cycles(self):
        """Test that multiple instrument/uninstrument cycles don't leak memory"""
        if not HAS_GETREFCOUNT:
            self.skipTest(
                "sys.getrefcount not available in this Python implementation"
            )

        app = fastapi.FastAPI()

        initial_refcount = sys.getrefcount(app)

        # Perform multiple instrument/uninstrument cycles
        for cycle_num in range(5):
            FastAPIInstrumentor.instrument_app(app)
            FastAPIInstrumentor.uninstrument_app(app)

        final_refcount = sys.getrefcount(app)

        # The refcount should not grow significantly after multiple cycles
        # (may not be exactly initial due to Python internals)
        self.assertLessEqual(
            final_refcount,
            initial_refcount
            + 2,  # Allow small increase due to Python internals
            f"Refcount after {cycle_num+1} instrument/uninstrument cycles should not grow significantly",
        )

        # Verify that the app is not in the set
        self.assertNotIn(
            app,
            _InstrumentedFastAPI._instrumented_fastapi_apps,
            "App should not be in _instrumented_fastapi_apps after uninstrument_app()",
        )

    def test_multiple_apps_instrument_uninstrument(self):
        """Test that multiple apps can be instrumented and uninstrumented without leaks"""
        if not HAS_GETREFCOUNT:
            self.skipTest(
                "sys.getrefcount not available in this Python implementation"
            )

        apps = [fastapi.FastAPI() for _ in range(3)]
        initial_refcounts = [sys.getrefcount(app) for app in apps]

        # Instrument all apps
        for app in apps:
            FastAPIInstrumentor.instrument_app(app)

        # Uninstrument all apps
        for app in apps:
            FastAPIInstrumentor.uninstrument_app(app)

        # Check that refcounts are not significantly increased
        for app_idx, app in enumerate(apps):
            final_refcount = sys.getrefcount(app)
            self.assertLessEqual(
                final_refcount,
                initial_refcounts[app_idx]
                + 2,  # Allow small increase due to Python internals
                f"App {app_idx} refcount should not grow significantly",
            )

        # Verify that no apps are in the set
        for app in apps:
            self.assertNotIn(
                app,
                _InstrumentedFastAPI._instrumented_fastapi_apps,
                "All apps should be removed from _instrumented_fastapi_apps",
            )

    def test_demonstrate_fix(self):
        """Demonstrate the fix for the memory leak issue"""
        app = fastapi.FastAPI()

        # Before the fix: app would remain in _instrumented_fastapi_apps after uninstrument_app()
        # After the fix: app should be removed from _instrumented_fastapi_apps

        FastAPIInstrumentor.instrument_app(app)

        # Verify app is in the set after instrumentation
        self.assertIn(app, _InstrumentedFastAPI._instrumented_fastapi_apps)

        FastAPIInstrumentor.uninstrument_app(app)

        # Verify app is removed from the set after uninstrumentation
        self.assertNotIn(app, _InstrumentedFastAPI._instrumented_fastapi_apps)
        self.assertEqual(
            len(_InstrumentedFastAPI._instrumented_fastapi_apps), 0
        )


if __name__ == "__main__":
    unittest.main()
