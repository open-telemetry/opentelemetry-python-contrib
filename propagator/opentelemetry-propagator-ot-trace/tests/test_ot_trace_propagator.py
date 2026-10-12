# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from unittest import TestCase

from opentelemetry.baggage import get_all, set_baggage
from opentelemetry.context import Context
from opentelemetry.propagators.ot_trace import (
    _MAX_BAGGAGE_BYTES_PER_ENTRY,
    _MAX_BAGGAGE_ENTRIES,
    _MAX_BAGGAGE_TOTAL_BYTES,
    OT_BAGGAGE_PREFIX,
    OT_SAMPLED_HEADER,
    OT_SPAN_ID_HEADER,
    OT_TRACE_ID_HEADER,
    OTTracePropagator,
)
from opentelemetry.propagators.textmap import Getter
from opentelemetry.sdk.trace import _Span
from opentelemetry.trace import (
    INVALID_TRACE_ID,
    SpanContext,
    TraceFlags,
    set_span_in_context,
)
from opentelemetry.trace.propagation import get_current_span


# pylint: disable=too-many-public-methods
class TestOTTracePropagator(TestCase):
    ot_trace_propagator = OTTracePropagator()

    def carrier_inject(self, trace_id, span_id, is_remote, trace_flags):
        carrier = {}

        self.ot_trace_propagator.inject(
            carrier,
            set_span_in_context(
                _Span(
                    "child",
                    context=SpanContext(
                        trace_id=trace_id,
                        span_id=span_id,
                        is_remote=is_remote,
                        trace_flags=trace_flags,
                    ),
                )
            ),
        )

        return carrier

    def test_inject_short_trace_id_short_span_id(self):
        carrier = self.carrier_inject(
            int("1", 16),
            int("2", 16),
            True,
            TraceFlags.SAMPLED,
        )

        self.assertEqual(carrier[OT_TRACE_ID_HEADER], "1")
        self.assertEqual(carrier[OT_SPAN_ID_HEADER], "2")

    def test_inject_trace_id_span_id_true(self):
        """Test valid trace_id, span_id and sampled true"""
        carrier = self.carrier_inject(
            int("80f198ee56343ba864fe8b2a57d3eff7", 16),
            int("e457b5a2e4d86bd1", 16),
            True,
            TraceFlags.SAMPLED,
        )

        self.assertEqual(carrier[OT_TRACE_ID_HEADER], "64fe8b2a57d3eff7")
        self.assertEqual(carrier[OT_SPAN_ID_HEADER], "e457b5a2e4d86bd1")
        self.assertEqual(carrier[OT_SAMPLED_HEADER], "true")

    def test_inject_trace_id_span_id_false(self):
        """Test valid trace_id, span_id and sampled true"""
        carrier = self.carrier_inject(
            int("80f198ee56343ba864fe8b2a57d3eff7", 16),
            int("e457b5a2e4d86bd1", 16),
            False,
            TraceFlags.DEFAULT,
        )

        self.assertEqual(carrier[OT_TRACE_ID_HEADER], "64fe8b2a57d3eff7")
        self.assertEqual(carrier[OT_SPAN_ID_HEADER], "e457b5a2e4d86bd1")
        self.assertEqual(carrier[OT_SAMPLED_HEADER], "false")

    def test_inject_truncate_traceid(self):
        """Test that traceid is truncated to 64 bits"""

        self.assertEqual(
            self.carrier_inject(
                int("80f198ee56343ba864fe8b2a57d3eff7", 16),
                int("e457b5a2e4d86bd1", 16),
                True,
                TraceFlags.DEFAULT,
            )[OT_TRACE_ID_HEADER],
            "64fe8b2a57d3eff7",
        )

    def test_inject_sampled_true(self):
        """Test that sampled true trace flags are injected"""

        self.assertEqual(
            self.carrier_inject(
                int("80f198ee56343ba864fe8b2a57d3eff7", 16),
                int("e457b5a2e4d86bd1", 16),
                True,
                TraceFlags.SAMPLED,
            )[OT_SAMPLED_HEADER],
            "true",
        )

    def test_inject_sampled_false(self):
        """Test that sampled false trace flags are injected"""

        self.assertEqual(
            self.carrier_inject(
                int("80f198ee56343ba864fe8b2a57d3eff7", 16),
                int("e457b5a2e4d86bd1", 16),
                True,
                TraceFlags.DEFAULT,
            )[OT_SAMPLED_HEADER],
            "false",
        )

    def test_inject_invalid_trace_id(self):
        """Test that no attributes are injected if the trace_id is invalid"""

        self.assertEqual(
            self.carrier_inject(
                INVALID_TRACE_ID,
                int("e457b5a2e4d86bd1", 16),
                True,
                TraceFlags.SAMPLED,
            ),
            {},
        )

    def test_inject_set_baggage(self):
        """Test that baggage is set"""

        carrier = {}

        self.ot_trace_propagator.inject(
            carrier,
            set_baggage(
                "key",
                "value",
                context=set_span_in_context(
                    _Span(
                        "child",
                        SpanContext(
                            trace_id=int("80f198ee56343ba864fe8b2a57d3eff7", 16),
                            span_id=int("e457b5a2e4d86bd1", 16),
                            is_remote=True,
                            trace_flags=TraceFlags.SAMPLED,
                        ),
                    )
                ),
            ),
        )

        self.assertEqual(carrier["".join([OT_BAGGAGE_PREFIX, "key"])], "value")

    def test_inject_invalid_baggage_keys(self):
        """Test that invalid baggage keys are not set"""

        carrier = {}

        self.ot_trace_propagator.inject(
            carrier,
            set_baggage(
                "(",
                "value",
                context=set_span_in_context(
                    _Span(
                        "child",
                        SpanContext(
                            trace_id=int("80f198ee56343ba864fe8b2a57d3eff7", 16),
                            span_id=int("e457b5a2e4d86bd1", 16),
                            is_remote=True,
                            trace_flags=TraceFlags.SAMPLED,
                        ),
                    )
                ),
            ),
        )

        self.assertNotIn("".join([OT_BAGGAGE_PREFIX, "!"]), carrier.keys())

    def test_inject_invalid_baggage_values(self):
        """Test that invalid baggage values are not set"""

        carrier = {}

        self.ot_trace_propagator.inject(
            carrier,
            set_baggage(
                "key",
                "α",
                context=set_span_in_context(
                    _Span(
                        "child",
                        SpanContext(
                            trace_id=int("80f198ee56343ba864fe8b2a57d3eff7", 16),
                            span_id=int("e457b5a2e4d86bd1", 16),
                            is_remote=True,
                            trace_flags=TraceFlags.SAMPLED,
                        ),
                    )
                ),
            ),
        )

        self.assertNotIn("".join([OT_BAGGAGE_PREFIX, "key"]), carrier.keys())

    def test_inject_baggage_count_capped_at_max(self):
        """Number of ot-baggage-* entries injected must be capped, so
        oversized contexts are not pushed to downstream services."""

        context = set_span_in_context(
            _Span(
                "child",
                SpanContext(
                    trace_id=int("80f198ee56343ba864fe8b2a57d3eff7", 16),
                    span_id=int("e457b5a2e4d86bd1", 16),
                    is_remote=True,
                    trace_flags=TraceFlags.SAMPLED,
                ),
            )
        )
        for idx in range(_MAX_BAGGAGE_ENTRIES + 50):
            context = set_baggage(f"k{idx}", f"v{idx}", context=context)

        carrier = {}
        with self.assertLogs("opentelemetry.propagators.ot_trace", level="WARNING") as cm:
            self.ot_trace_propagator.inject(carrier, context)

        injected = [k for k in carrier if k.startswith(OT_BAGGAGE_PREFIX)]
        self.assertEqual(len(injected), _MAX_BAGGAGE_ENTRIES)
        self.assertTrue(any("maximum number of list-members" in m for m in cm.output))

    def test_inject_baggage_per_entry_byte_cap(self):
        """Per-entry byte length (key + value) must be capped on inject."""

        context = set_span_in_context(
            _Span(
                "child",
                SpanContext(
                    trace_id=int("80f198ee56343ba864fe8b2a57d3eff7", 16),
                    span_id=int("e457b5a2e4d86bd1", 16),
                    is_remote=True,
                    trace_flags=TraceFlags.SAMPLED,
                ),
            )
        )
        context = set_baggage("ok", "fits", context=context)
        context = set_baggage("big", "a" * (_MAX_BAGGAGE_BYTES_PER_ENTRY + 1), context=context)

        carrier = {}
        with self.assertLogs("opentelemetry.propagators.ot_trace", level="WARNING") as cm:
            self.ot_trace_propagator.inject(carrier, context)

        self.assertIn("".join([OT_BAGGAGE_PREFIX, "ok"]), carrier)
        self.assertNotIn("".join([OT_BAGGAGE_PREFIX, "big"]), carrier)
        self.assertTrue(any("bytes per list-member" in m for m in cm.output))

    def test_inject_baggage_total_byte_cap(self):
        """Cumulative byte length across all entries must be capped on inject."""

        context = set_span_in_context(
            _Span(
                "child",
                SpanContext(
                    trace_id=int("80f198ee56343ba864fe8b2a57d3eff7", 16),
                    span_id=int("e457b5a2e4d86bd1", 16),
                    is_remote=True,
                    trace_flags=TraceFlags.SAMPLED,
                ),
            )
        )
        chunk_val = "a" * (_MAX_BAGGAGE_TOTAL_BYTES // 3)
        context = set_baggage("k1", chunk_val, context=context)
        context = set_baggage("k2", chunk_val, context=context)
        context = set_baggage("k3", chunk_val, context=context)

        carrier = {}
        with self.assertLogs("opentelemetry.propagators.ot_trace", level="WARNING") as cm:
            self.ot_trace_propagator.inject(carrier, context)

        injected = [k for k in carrier if k.startswith(OT_BAGGAGE_PREFIX)]
        self.assertEqual(len(injected), 2)
        self.assertIn("".join([OT_BAGGAGE_PREFIX, "k1"]), carrier)
        self.assertIn("".join([OT_BAGGAGE_PREFIX, "k2"]), carrier)
        self.assertNotIn("".join([OT_BAGGAGE_PREFIX, "k3"]), carrier)
        self.assertTrue(any("maximum number of total bytes" in m for m in cm.output))

    def test_inject_baggage_oversized_flood_is_bounded(self):
        """A flood of oversized entries after the cap must not keep the
        inject loop iterating: oversized entries count toward the cap, so
        the loop stops after _MAX_BAGGAGE_ENTRIES entries are processed."""

        context = set_span_in_context(
            _Span(
                "child",
                SpanContext(
                    trace_id=int("80f198ee56343ba864fe8b2a57d3eff7", 16),
                    span_id=int("e457b5a2e4d86bd1", 16),
                    is_remote=True,
                    trace_flags=TraceFlags.SAMPLED,
                ),
            )
        )
        oversized_value = "a" * (_MAX_BAGGAGE_BYTES_PER_ENTRY + 1)
        for idx in range(_MAX_BAGGAGE_ENTRIES + 50):
            context = set_baggage(f"big{idx}", oversized_value, context=context)

        carrier = {}
        with self.assertLogs("opentelemetry.propagators.ot_trace", level="WARNING") as cm:
            self.ot_trace_propagator.inject(carrier, context)

        injected = [k for k in carrier if k.startswith(OT_BAGGAGE_PREFIX)]
        self.assertEqual(len(injected), 0)
        # _MAX_BAGGAGE_ENTRIES per-entry warnings + 1 count-exceeded warning
        self.assertEqual(len(cm.output), _MAX_BAGGAGE_ENTRIES + 1)
        self.assertTrue(any("maximum number of list-members" in m for m in cm.output))

    def test_inject_baggage_invalid_flood_is_bounded(self):
        """A flood of invalid entries after the cap must not keep the
        inject loop iterating: invalid entries count toward the cap, so
        the loop stops after _MAX_BAGGAGE_ENTRIES entries are processed."""

        context = set_span_in_context(
            _Span(
                "child",
                SpanContext(
                    trace_id=int("80f198ee56343ba864fe8b2a57d3eff7", 16),
                    span_id=int("e457b5a2e4d86bd1", 16),
                    is_remote=True,
                    trace_flags=TraceFlags.SAMPLED,
                ),
            )
        )
        for idx in range(_MAX_BAGGAGE_ENTRIES + 50):
            # Invalid header name containing illegal characters (space)
            context = set_baggage(f"bad key {idx}", f"val{idx}", context=context)

        carrier = {}
        with self.assertLogs("opentelemetry.propagators.ot_trace", level="WARNING") as cm:
            self.ot_trace_propagator.inject(carrier, context)

        injected = [k for k in carrier if k.startswith(OT_BAGGAGE_PREFIX)]
        self.assertEqual(len(injected), 0)
        self.assertEqual(len(cm.output), 1)
        self.assertTrue(any("maximum number of list-members" in m for m in cm.output))

    def test_extract_trace_id_span_id_sampled_true(self):
        """Test valid trace_id, span_id and sampled true"""

        span_context = get_current_span(
            self.ot_trace_propagator.extract(
                {
                    OT_TRACE_ID_HEADER: "80f198ee56343ba864fe8b2a57d3eff7",
                    OT_SPAN_ID_HEADER: "e457b5a2e4d86bd1",
                    OT_SAMPLED_HEADER: "true",
                },
            )
        ).get_span_context()

        self.assertEqual(hex(span_context.trace_id)[2:], "80f198ee56343ba864fe8b2a57d3eff7")
        self.assertEqual(hex(span_context.span_id)[2:], "e457b5a2e4d86bd1")
        self.assertTrue(span_context.is_remote)
        self.assertEqual(span_context.trace_flags, TraceFlags.SAMPLED)
        self.assertIsInstance(get_current_span().get_span_context().trace_flags, TraceFlags)

    def test_extract_trace_id_span_id_sampled_false(self):
        """Test valid trace_id, span_id and sampled false"""

        span_context = get_current_span(
            self.ot_trace_propagator.extract(
                {
                    OT_TRACE_ID_HEADER: "80f198ee56343ba864fe8b2a57d3eff7",
                    OT_SPAN_ID_HEADER: "e457b5a2e4d86bd1",
                    OT_SAMPLED_HEADER: "false",
                },
            )
        ).get_span_context()

        self.assertEqual(hex(span_context.trace_id)[2:], "80f198ee56343ba864fe8b2a57d3eff7")
        self.assertEqual(hex(span_context.span_id)[2:], "e457b5a2e4d86bd1")
        self.assertTrue(span_context.is_remote)
        self.assertEqual(span_context.trace_flags, TraceFlags.DEFAULT)
        self.assertIsInstance(get_current_span().get_span_context().trace_flags, TraceFlags)

    def test_extract_invalid_trace_header_to_explict_ctx(self):
        invalid_headers = [
            ("abc123!", "e457b5a2e4d86bd1"),  # malformed trace id
            ("64fe8b2a57d3eff7", "abc123!"),  # malformed span id
            ("0" * 32, "e457b5a2e4d86bd1"),  # invalid trace id
            ("64fe8b2a57d3eff7", "0" * 16),  # invalid span id
        ]
        for trace_id, span_id in invalid_headers:
            with self.subTest(trace_id=trace_id, span_id=span_id):
                orig_ctx = Context({"k1": "v1"})

                ctx = self.ot_trace_propagator.extract(
                    {
                        OT_TRACE_ID_HEADER: trace_id,
                        OT_SPAN_ID_HEADER: span_id,
                        OT_SAMPLED_HEADER: "false",
                    },
                    orig_ctx,
                )
                self.assertDictEqual(orig_ctx, ctx)

    def test_extract_invalid_trace_header_to_implicit_ctx(self):
        invalid_headers = [
            ("abc123!", "e457b5a2e4d86bd1"),  # malformed trace id
            ("64fe8b2a57d3eff7", "abc123!"),  # malformed span id
            ("0" * 32, "e457b5a2e4d86bd1"),  # invalid trace id
            ("64fe8b2a57d3eff7", "0" * 16),  # invalid span id
        ]
        for trace_id, span_id in invalid_headers:
            with self.subTest(trace_id=trace_id, span_id=span_id):
                ctx = self.ot_trace_propagator.extract(
                    {
                        OT_TRACE_ID_HEADER: trace_id,
                        OT_SPAN_ID_HEADER: span_id,
                        OT_SAMPLED_HEADER: "false",
                    }
                )
                self.assertDictEqual(Context(), ctx)

    def test_extract_baggage(self):
        """Test baggage extraction"""

        context = self.ot_trace_propagator.extract(
            {
                OT_TRACE_ID_HEADER: "64fe8b2a57d3eff7",
                OT_SPAN_ID_HEADER: "e457b5a2e4d86bd1",
                OT_SAMPLED_HEADER: "false",
                "".join([OT_BAGGAGE_PREFIX, "abc"]): "abc",
                "".join([OT_BAGGAGE_PREFIX, "def"]): "def",
            },
        )
        span_context = get_current_span(context).get_span_context()

        self.assertEqual(hex(span_context.trace_id)[2:], "64fe8b2a57d3eff7")
        self.assertEqual(hex(span_context.span_id)[2:], "e457b5a2e4d86bd1")
        self.assertTrue(span_context.is_remote)
        self.assertEqual(span_context.trace_flags, TraceFlags.DEFAULT)

        baggage = get_all(context)

        self.assertEqual(baggage["abc"], "abc")
        self.assertEqual(baggage["def"], "def")

    def test_extract_empty_to_explicit_ctx(self):
        """Test extraction when no headers are present"""
        orig_ctx = Context({"k1": "v1"})
        ctx = self.ot_trace_propagator.extract({}, orig_ctx)

        self.assertDictEqual(orig_ctx, ctx)

    def test_extract_empty_to_implicit_ctx(self):
        ctx = self.ot_trace_propagator.extract({})
        self.assertDictEqual(Context(), ctx)

    def test_extract_baggage_count_capped_at_max(self):
        """Number of ot-baggage-* entries recorded must be capped.

        Mirrors W3CBaggagePropagator and OTel SDK baggage limits (180 list-members).
        """
        carrier = {
            OT_TRACE_ID_HEADER: "64fe8b2a57d3eff7",
            OT_SPAN_ID_HEADER: "e457b5a2e4d86bd1",
            OT_SAMPLED_HEADER: "false",
        }
        # Construct (cap + 50) ot-baggage-* entries.
        for idx in range(_MAX_BAGGAGE_ENTRIES + 50):
            carrier["".join([OT_BAGGAGE_PREFIX, f"k{idx}"])] = f"v{idx}"

        with self.assertLogs("opentelemetry.propagators.ot_trace", level="WARNING") as cm:
            context = self.ot_trace_propagator.extract(carrier)
        baggage = get_all(context)
        self.assertEqual(len(baggage), _MAX_BAGGAGE_ENTRIES)
        self.assertTrue(any("exceeded the maximum number" in m for m in cm.output))

    def test_extract_baggage_per_entry_byte_cap(self):
        """Per-entry byte length (key + value) must be capped."""
        carrier = {
            OT_TRACE_ID_HEADER: "64fe8b2a57d3eff7",
            OT_SPAN_ID_HEADER: "e457b5a2e4d86bd1",
            OT_SAMPLED_HEADER: "false",
            "".join([OT_BAGGAGE_PREFIX, "ok"]): "fits",
            "".join([OT_BAGGAGE_PREFIX, "big"]): "a" * (_MAX_BAGGAGE_BYTES_PER_ENTRY + 1),
            # A long key alone (with prefix stripped) also trips the cap.
            "".join([OT_BAGGAGE_PREFIX, "k" * (_MAX_BAGGAGE_BYTES_PER_ENTRY + 1)]): "v",
        }
        with self.assertLogs("opentelemetry.propagators.ot_trace", level="WARNING") as cm:
            context = self.ot_trace_propagator.extract(carrier)
        baggage = get_all(context)
        self.assertIn("ok", baggage)
        self.assertNotIn("big", baggage)
        self.assertEqual(len(baggage), 1)
        self.assertTrue(any("bytes per list-member" in m for m in cm.output))

    def test_extract_baggage_total_byte_cap(self):
        """Cumulative byte length across all entries must be capped on extract."""
        chunk_val = "a" * (_MAX_BAGGAGE_TOTAL_BYTES // 3)
        carrier = {
            OT_TRACE_ID_HEADER: "64fe8b2a57d3eff7",
            OT_SPAN_ID_HEADER: "e457b5a2e4d86bd1",
            OT_SAMPLED_HEADER: "false",
            "".join([OT_BAGGAGE_PREFIX, "k1"]): chunk_val,
            "".join([OT_BAGGAGE_PREFIX, "k2"]): chunk_val,
            "".join([OT_BAGGAGE_PREFIX, "k3"]): chunk_val,
        }
        with self.assertLogs("opentelemetry.propagators.ot_trace", level="WARNING") as cm:
            context = self.ot_trace_propagator.extract(carrier)
        baggage = get_all(context)
        self.assertIn("k1", baggage)
        self.assertIn("k2", baggage)
        self.assertNotIn("k3", baggage)
        self.assertEqual(len(baggage), 2)
        self.assertTrue(any("maximum number of total bytes" in m for m in cm.output))

    def test_extract_baggage_existing_context_counts_toward_cap(self):
        """Pre-existing context baggage items count toward the entry cap."""
        context = Context()
        for idx in range(10):
            context = set_baggage(f"init{idx}", f"v{idx}", context=context)

        carrier = {
            OT_TRACE_ID_HEADER: "64fe8b2a57d3eff7",
            OT_SPAN_ID_HEADER: "e457b5a2e4d86bd1",
            OT_SAMPLED_HEADER: "false",
        }
        # Offer 180 new entries from carrier
        for idx in range(_MAX_BAGGAGE_ENTRIES):
            carrier["".join([OT_BAGGAGE_PREFIX, f"k{idx}"])] = f"v{idx}"

        with self.assertLogs("opentelemetry.propagators.ot_trace", level="WARNING") as cm:
            extracted_context = self.ot_trace_propagator.extract(carrier, context=context)

        baggage = get_all(extracted_context)
        self.assertEqual(len(baggage), _MAX_BAGGAGE_ENTRIES)
        for idx in range(10):
            self.assertIn(f"init{idx}", baggage)
        self.assertTrue(any("maximum number of list-members" in m for m in cm.output))

    def test_extract_baggage_oversized_flood_is_bounded(self):
        """A flood of oversized entries after the cap must not keep the
        extract loop iterating: oversized entries count toward the cap, so
        the loop stops after _MAX_BAGGAGE_ENTRIES entries are processed.

        Covers the "180 valid + many oversized" attack: without counting
        oversized entries the loop would walk every header.
        """
        oversized_value = "a" * (_MAX_BAGGAGE_BYTES_PER_ENTRY + 1)
        flood = 100_000

        class CountingGetter(Getter):
            def __init__(self):
                self.examined = 0

            def get(self, carrier, key):
                if key.startswith(OT_BAGGAGE_PREFIX):
                    self.examined += 1
                    return [carrier[key]]
                return [carrier[key]] if key in carrier else None

            def keys(self, carrier):
                return list(carrier.keys())

        carrier = {
            OT_TRACE_ID_HEADER: "64fe8b2a57d3eff7",
            OT_SPAN_ID_HEADER: "e457b5a2e4d86bd1",
            OT_SAMPLED_HEADER: "false",
        }
        # _MAX_BAGGAGE_ENTRIES valid entries first ...
        for idx in range(_MAX_BAGGAGE_ENTRIES):
            carrier["".join([OT_BAGGAGE_PREFIX, f"k{idx}"])] = f"v{idx}"
        # ... then a flood of oversized entries.
        for idx in range(flood):
            carrier["".join([OT_BAGGAGE_PREFIX, f"big{idx}"])] = oversized_value

        getter = CountingGetter()
        with self.assertLogs("opentelemetry.propagators.ot_trace", level="WARNING") as cm:
            context = self.ot_trace_propagator.extract(carrier, getter=getter)

        baggage = get_all(context)
        # Only the valid entries are recorded.
        self.assertEqual(len(baggage), _MAX_BAGGAGE_ENTRIES)
        # The loop hard-breaks after the cap: at most cap + 1 entries are
        # ever examined regardless of how many oversized ones follow.
        self.assertLessEqual(getter.examined, _MAX_BAGGAGE_ENTRIES + 1)
        self.assertTrue(any("maximum number of list-members" in m for m in cm.output))

    def test_extract_baggage_none_value_does_not_count_toward_cap(self):
        """ot-baggage-* entries with no value are skipped silently and do
        not count toward the entry cap."""

        class NoneGetter(Getter):
            # Returns None for every ot-baggage-* key, mimicking a carrier
            # whose getter cannot resolve the header (e.g. drained iterator).
            def get(self, carrier, key):
                if key.startswith(OT_BAGGAGE_PREFIX):
                    return None
                return [carrier[key]] if key in carrier else None

            def keys(self, carrier):
                return list(carrier.keys())

        carrier = {
            OT_TRACE_ID_HEADER: "64fe8b2a57d3eff7",
            OT_SPAN_ID_HEADER: "e457b5a2e4d86bd1",
            OT_SAMPLED_HEADER: "false",
        }
        # 5 ot-baggage-* keys whose values resolve to None.
        for idx in range(5):
            carrier["".join([OT_BAGGAGE_PREFIX, f"k{idx}"])] = "ignored"

        context = self.ot_trace_propagator.extract(carrier, getter=NoneGetter())
        baggage = get_all(context)
        self.assertEqual(baggage, {})
