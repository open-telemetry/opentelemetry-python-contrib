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

import unittest

from google.genai import types as genai_types
from .base import TestCase

class FinishReasonsTestCase(TestCase):

    def generate_and_get_span_finish_reasons(self):
        self.client.models.generate_content(
            model='gemini-2.5-flash-001',
            contents='Some prompt')
        span = self.otel.get_span_named("generate_content gemini-2.5-flash-001")
        assert span is not None
        assert "gen_ai.response.finish_reasons" in span.attributes
        return list(span.attributes["gen_ai.response.finish_reasons"])

    def test_single_candidate_with_valid_reason(self):
        self.configure_valid_response(candidate=genai_types.Candidate(
            finish_reason=genai_types.FinishReason.STOP
        ))
        self.assertEqual(
            self.generate_and_get_span_finish_reasons(),
            ["stop"])

    def test_single_candidate_with_safety_reason(self):
        self.configure_valid_response(candidate=genai_types.Candidate(
            finish_reason=genai_types.FinishReason.SAFETY
        ))
        self.assertEqual(
            self.generate_and_get_span_finish_reasons(),
            ["safety"])

    def test_single_candidate_with_max_tokens_reason(self):
        self.configure_valid_response(candidate=genai_types.Candidate(
            finish_reason=genai_types.FinishReason.MAX_TOKENS
        ))
        self.assertEqual(
            self.generate_and_get_span_finish_reasons(),
            ["max_tokens"])

    def test_single_candidate_with_no_reason(self):
        self.configure_valid_response(candidate=genai_types.Candidate(
            finish_reason=None
        ))
        self.assertEqual(
            self.generate_and_get_span_finish_reasons(),
            [])

    def test_single_candidate_with_unspecified_reason(self):
        self.configure_valid_response(candidate=genai_types.Candidate(
            finish_reason=genai_types.FinishReason.FINISH_REASON_UNSPECIFIED
        ))
        self.assertEqual(
            self.generate_and_get_span_finish_reasons(),
            ["unspecified"])

    def test_multiple_candidates_with_valid_reasons(self):
        self.configure_valid_response(candidates=[
            genai_types.Candidate(finish_reason=genai_types.FinishReason.MAX_TOKENS),
            genai_types.Candidate(finish_reason=genai_types.FinishReason.STOP),
        ])
        self.assertEqual(
            self.generate_and_get_span_finish_reasons(),
            ["max_tokens", "stop"])

    def test_sorts_finish_reasons(self):
        self.configure_valid_response(candidates=[
            genai_types.Candidate(finish_reason=genai_types.FinishReason.STOP),
            genai_types.Candidate(finish_reason=genai_types.FinishReason.MAX_TOKENS),
            genai_types.Candidate(finish_reason=genai_types.FinishReason.SAFETY),
        ])
        self.assertEqual(
            self.generate_and_get_span_finish_reasons(),
            ["max_tokens", "safety", "stop"])

    def test_deduplicates_finish_reasons(self):
        self.configure_valid_response(candidates=[
            genai_types.Candidate(finish_reason=genai_types.FinishReason.STOP),
            genai_types.Candidate(finish_reason=genai_types.FinishReason.MAX_TOKENS),
            genai_types.Candidate(finish_reason=genai_types.FinishReason.STOP),
            genai_types.Candidate(finish_reason=genai_types.FinishReason.STOP),
            genai_types.Candidate(finish_reason=genai_types.FinishReason.SAFETY),
            genai_types.Candidate(finish_reason=genai_types.FinishReason.STOP),
            genai_types.Candidate(finish_reason=genai_types.FinishReason.STOP),
            genai_types.Candidate(finish_reason=genai_types.FinishReason.STOP),
        ])
        self.assertEqual(
            self.generate_and_get_span_finish_reasons(),
            ["max_tokens", "safety", "stop"])
