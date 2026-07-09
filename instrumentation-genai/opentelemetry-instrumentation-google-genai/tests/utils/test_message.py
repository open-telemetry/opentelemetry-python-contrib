# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import unittest

from google.genai import types as genai_types

from opentelemetry.instrumentation.google_genai.message import (
    _to_finish_reason,
)


class ToFinishReasonTest(unittest.TestCase):
    def test_none_maps_to_empty_string(self):
        self.assertEqual(_to_finish_reason(None), "")

    def test_stop(self):
        self.assertEqual(
            _to_finish_reason(genai_types.FinishReason.STOP), "stop"
        )

    def test_max_tokens_maps_to_length(self):
        self.assertEqual(
            _to_finish_reason(genai_types.FinishReason.MAX_TOKENS), "length"
        )

    def test_unspecified_maps_to_error(self):
        self.assertEqual(
            _to_finish_reason(
                genai_types.FinishReason.FINISH_REASON_UNSPECIFIED
            ),
            "error",
        )

    def test_other_maps_to_error(self):
        self.assertEqual(
            _to_finish_reason(genai_types.FinishReason.OTHER), "error"
        )

    def test_content_filter_reasons(self):
        for reason in (
            genai_types.FinishReason.SAFETY,
            genai_types.FinishReason.RECITATION,
            genai_types.FinishReason.BLOCKLIST,
            genai_types.FinishReason.PROHIBITED_CONTENT,
            genai_types.FinishReason.SPII,
            genai_types.FinishReason.IMAGE_SAFETY,
            genai_types.FinishReason.IMAGE_PROHIBITED_CONTENT,
        ):
            with self.subTest(reason=reason):
                self.assertEqual(_to_finish_reason(reason), "content_filter")

    def test_error_reasons(self):
        for reason in (
            genai_types.FinishReason.MALFORMED_FUNCTION_CALL,
            genai_types.FinishReason.UNEXPECTED_TOOL_CALL,
        ):
            with self.subTest(reason=reason):
                self.assertEqual(_to_finish_reason(reason), "error")

    def test_unmapped_reason_falls_back_to_name(self):
        # LANGUAGE has no dedicated OTel mapping and should be passed through
        # using the raw enum name.
        self.assertEqual(
            _to_finish_reason(genai_types.FinishReason.LANGUAGE), "LANGUAGE"
        )
