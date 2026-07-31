# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
# type: ignore

from unittest import TestCase
from unittest.mock import patch


class TestSiteCustomize(TestCase):
    # pylint:disable=import-outside-toplevel,unused-import,no-self-use
    @patch("opentelemetry.instrumentation.auto_instrumentation.initialize")
    def test_sitecustomize_side_effects(self, initialize_mock):
        initialize_mock.assert_not_called()

        import opentelemetry.instrumentation.auto_instrumentation.sitecustomize  # NOQA

        initialize_mock.assert_called_once()
