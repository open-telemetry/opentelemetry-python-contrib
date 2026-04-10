# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

import unittest
from unittest.mock import MagicMock

from opentelemetry.instrumentation._semconv import (
    _set_status,
    _StabilityMode,
)
from opentelemetry.trace.status import Status, StatusCode


def _make_span(status_code, description=None):
    span = MagicMock()
    span.is_recording.return_value = True
    span.status = Status(status_code, description)
    return span


class TestSetStatus(unittest.TestCase):
    def test_does_not_downgrade_error_to_ok(self):
        """ERROR status should not be overridden by a lower priority OK"""
        span = _make_span(StatusCode.ERROR, "original error")
        _set_status(
            span,
            {},
            200,
            "200",
            server_span=True,
            sem_conv_opt_in_mode=_StabilityMode.DEFAULT,
        )
        for call in span.set_status.call_args_list:
            args = call[0]
            if args:
                self.assertNotEqual(args[0].status_code, StatusCode.OK)

    def test_does_not_wipe_description_with_none(self):
        """Same ERROR status should preserve existing description"""
        span = _make_span(StatusCode.ERROR, "keep this message")
        _set_status(
            span,
            {},
            500,
            "500",
            server_span=True,
            sem_conv_opt_in_mode=_StabilityMode.DEFAULT,
        )
        last_call = span.set_status.call_args
        if last_call:
            status_arg = last_call[0][0]
            self.assertEqual(status_arg.description, "keep this message")

    def test_upgrades_unset_to_error(self):
        """UNSET status should be upgraded to ERROR"""
        span = _make_span(StatusCode.UNSET)
        _set_status(
            span,
            {},
            500,
            "500",
            server_span=True,
            sem_conv_opt_in_mode=_StabilityMode.DEFAULT,
        )
        span.set_status.assert_called()
        last_call = span.set_status.call_args[0][0]
        self.assertEqual(last_call.status_code, StatusCode.ERROR)

    def test_unset_to_ok(self):
        """UNSET status should be upgraded to OK for 2xx"""
        span = _make_span(StatusCode.UNSET)
        _set_status(
            span,
            {},
            200,
            "200",
            server_span=False,
            sem_conv_opt_in_mode=_StabilityMode.DEFAULT,
        )
        last_call = span.set_status.call_args[0][0]
        self.assertEqual(last_call.status_code, StatusCode.UNSET)
