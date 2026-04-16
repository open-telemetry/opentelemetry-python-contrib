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


from opentelemetry.instrumentation.langchain.utils import (
    extract_propagation_context,
    extract_trace_headers,
    propagated_context,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import get_current_span

# Valid W3C traceparent components for test fixtures.
_TRACE_ID = "0af7651916cd43dd8448eb211c80319c"
_SPAN_ID = "b7ad6b7169203331"
_TRACEPARENT = f"00-{_TRACE_ID}-{_SPAN_ID}-01"
_TRACESTATE = "congo=t61rcWkgMzE"


# ---------------------------------------------------------------------------
# extract_trace_headers
# ---------------------------------------------------------------------------


class TestExtractTraceHeaders:
    """Tests for extract_trace_headers()."""

    def test_top_level_traceparent(self):
        container = {"traceparent": _TRACEPARENT}
        result = extract_trace_headers(container)
        assert result == {"traceparent": _TRACEPARENT}

    def test_top_level_traceparent_and_tracestate(self):
        container = {"traceparent": _TRACEPARENT, "tracestate": _TRACESTATE}
        result = extract_trace_headers(container)
        assert result == {
            "traceparent": _TRACEPARENT,
            "tracestate": _TRACESTATE,
        }

    def test_nested_headers_key(self):
        container = {"headers": {"traceparent": _TRACEPARENT}}
        result = extract_trace_headers(container)
        assert result == {"traceparent": _TRACEPARENT}

    def test_nested_metadata_key(self):
        container = {
            "metadata": {
                "traceparent": _TRACEPARENT,
                "tracestate": _TRACESTATE,
            }
        }
        result = extract_trace_headers(container)
        assert result == {
            "traceparent": _TRACEPARENT,
            "tracestate": _TRACESTATE,
        }

    def test_nested_request_headers_key(self):
        container = {"request_headers": {"traceparent": _TRACEPARENT}}
        result = extract_trace_headers(container)
        assert result == {"traceparent": _TRACEPARENT}

    def test_empty_container_returns_none(self):
        assert extract_trace_headers({}) is None

    def test_no_trace_headers_returns_none(self):
        container = {"foo": "bar", "headers": {"content-type": "text/plain"}}
        assert extract_trace_headers(container) is None

    def test_non_dict_container_returns_none(self):
        assert extract_trace_headers(None) is None
        assert extract_trace_headers("string") is None
        assert extract_trace_headers(42) is None
        assert extract_trace_headers(["traceparent", _TRACEPARENT]) is None

    def test_empty_string_traceparent_ignored(self):
        container = {"traceparent": ""}
        assert extract_trace_headers(container) is None

    def test_top_level_takes_precedence_over_nested(self):
        other_traceparent = (
            "00-11111111111111111111111111111111-2222222222222222-01"
        )
        container = {
            "traceparent": _TRACEPARENT,
            "headers": {"traceparent": other_traceparent},
        }
        result = extract_trace_headers(container)
        assert result["traceparent"] == _TRACEPARENT


# ---------------------------------------------------------------------------
# propagated_context
# ---------------------------------------------------------------------------


class TestPropagatedContext:
    """Tests for the propagated_context() context manager."""

    def test_noop_when_headers_is_none(self):
        with propagated_context(None):
            span = get_current_span()
            assert not span.get_span_context().is_valid

    def test_noop_when_headers_is_empty(self):
        with propagated_context({}):
            span = get_current_span()
            assert not span.get_span_context().is_valid

    def test_attaches_and_detaches_valid_traceparent(self):
        provider = TracerProvider()
        tracer = provider.get_tracer("test")

        with tracer.start_as_current_span("outer"):
            outer_ctx = get_current_span().get_span_context()

            headers = {"traceparent": _TRACEPARENT}
            with propagated_context(headers):
                inner_ctx = get_current_span().get_span_context()
                # The propagated context should carry the injected trace id.
                assert format(inner_ctx.trace_id, "032x") == _TRACE_ID

            # After exiting, we should be back to the outer span.
            restored_ctx = get_current_span().get_span_context()
            assert restored_ctx.trace_id == outer_ctx.trace_id

        provider.shutdown()

    def test_invalid_traceparent_does_not_crash(self):
        headers = {"traceparent": "not-a-valid-traceparent"}
        with propagated_context(headers):
            # Should execute without raising; span context may be invalid.
            span = get_current_span()
            assert span is not None

    def test_malformed_traceparent_does_not_crash(self):
        headers = {"traceparent": "00-short-bad-01"}
        with propagated_context(headers):
            span = get_current_span()
            assert span is not None


# ---------------------------------------------------------------------------
# extract_propagation_context
# ---------------------------------------------------------------------------


class TestExtractPropagationContext:
    """Tests for extract_propagation_context()."""

    def test_finds_headers_in_metadata(self):
        metadata = {"traceparent": _TRACEPARENT}
        result = extract_propagation_context(metadata, {}, {})
        assert result == {"traceparent": _TRACEPARENT}

    def test_falls_back_to_inputs(self):
        inputs = {"traceparent": _TRACEPARENT}
        result = extract_propagation_context({}, inputs, {})
        assert result == {"traceparent": _TRACEPARENT}

    def test_falls_back_to_kwargs(self):
        kwargs = {"traceparent": _TRACEPARENT}
        result = extract_propagation_context({}, {}, kwargs)
        assert result == {"traceparent": _TRACEPARENT}

    def test_returns_none_when_no_source_has_headers(self):
        result = extract_propagation_context({}, {}, {})
        assert result is None

    def test_metadata_takes_precedence_over_inputs(self):
        other_traceparent = (
            "00-11111111111111111111111111111111-2222222222222222-01"
        )
        metadata = {"traceparent": _TRACEPARENT}
        inputs = {"traceparent": other_traceparent}
        result = extract_propagation_context(metadata, inputs, {})
        assert result["traceparent"] == _TRACEPARENT

    def test_none_sources_are_skipped(self):
        kwargs = {"traceparent": _TRACEPARENT}
        result = extract_propagation_context(None, None, kwargs)
        assert result == {"traceparent": _TRACEPARENT}

    def test_non_dict_inputs_skipped(self):
        result = extract_propagation_context(
            None, "not a dict", {"traceparent": _TRACEPARENT}
        )
        assert result == {"traceparent": _TRACEPARENT}
