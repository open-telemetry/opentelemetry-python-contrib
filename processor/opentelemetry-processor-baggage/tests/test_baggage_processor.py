# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import re
import unittest
from importlib.metadata import entry_points

from opentelemetry.baggage import get_all as get_all_baggage
from opentelemetry.baggage import set_baggage
from opentelemetry.context import attach, detach
from opentelemetry.processor.baggage import (
    ALLOW_ALL_BAGGAGE_KEYS,
    BaggageSpanProcessor,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SpanProcessor
from opentelemetry.trace import Span, Tracer

# (included, excluded, baggage keys, expected copied keys)
_INCLUDE_EXCLUDE_CASES = (
    (None, None, ["a", "b"], ["a", "b"]),
    ([], [], ["a", "b"], ["a", "b"]),
    (["a*"], None, ["a", "ab", "b"], ["a", "ab"]),
    (None, ["a*"], ["a", "ab", "b"], ["b"]),
    (["a*", "b*"], ["ab*"], ["a", "ab", "abc", "b", "c"], ["a", "b"]),
    (["a", "b"], ["a"], ["a", "b", "c"], ["b"]),
    (["a?c"], None, ["abc", "ac", "abbc"], ["abc"]),
    (["foo"], None, ["foo", "foobar", "xfoo", "FOO"], ["foo"]),
    (["a.b", "[c]", "d+"], None, ["a.b", "axb", "[c]", "c", "d+", "dd"], ["a.b", "[c]", "d+"]),
)


def _baggage_context(keys):
    ctx = None
    for key in keys:
        ctx = set_baggage(key, "value", context=ctx)
    return ctx


class BaggageSpanProcessorTest(unittest.TestCase):
    def test_check_the_baggage(self):
        self.assertIsInstance(BaggageSpanProcessor(ALLOW_ALL_BAGGAGE_KEYS), SpanProcessor)

    def test_set_baggage_attaches_to_child_spans_and_detaches_properly_with_context(
        self,
    ):
        tracer_provider = TracerProvider()
        tracer_provider.add_span_processor(BaggageSpanProcessor(ALLOW_ALL_BAGGAGE_KEYS))

        # tracer has no baggage to start
        tracer = tracer_provider.get_tracer("my-tracer")
        self.assertIsInstance(tracer, Tracer)
        self.assertEqual(get_all_baggage(), {})
        # set baggage in context
        ctx = set_baggage("queen", "bee")
        with tracer.start_as_current_span(name="bumble", context=ctx) as bumble_span:
            # span should have baggage key-value pair in context
            self.assertEqual(get_all_baggage(ctx), {"queen": "bee"})
            # span should have baggage key-value pair in attribute
            self.assertEqual(bumble_span._attributes["queen"], "bee")
            with tracer.start_as_current_span(name="child_span", context=ctx) as child_span:
                self.assertIsInstance(child_span, Span)
                # child span should have baggage key-value pair in context
                self.assertEqual(get_all_baggage(ctx), {"queen": "bee"})
                # child span should have baggage key-value pair in attribute
                self.assertEqual(child_span._attributes["queen"], "bee")

    def test_baggage_span_processor_with_string_prefix(
        self,
    ):
        tracer_provider = TracerProvider()
        tracer_provider.add_span_processor(BaggageSpanProcessor(self.has_prefix))

        # tracer has no baggage to start
        tracer = tracer_provider.get_tracer("my-tracer")
        self.assertIsInstance(tracer, Tracer)
        self.assertEqual(get_all_baggage(), {})
        # set baggage in context
        ctx = set_baggage("queen", "bee")
        with tracer.start_as_current_span(name="bumble", context=ctx) as bumble_span:
            # span should have baggage key-value pair in context
            self.assertEqual(get_all_baggage(ctx), {"queen": "bee"})
            # span should have baggage key-value pair in attribute
            self.assertEqual(bumble_span._attributes["queen"], "bee")
            with tracer.start_as_current_span(name="child_span", context=ctx) as child_span:
                self.assertIsInstance(child_span, Span)
                # child span should have baggage key-value pair in context
                self.assertEqual(get_all_baggage(ctx), {"queen": "bee"})
                # child span should have baggage key-value pair in attribute
                self.assertEqual(child_span._attributes["queen"], "bee")

    def test_baggage_span_processor_with_regex(
        self,
    ):
        tracer_provider = TracerProvider()
        tracer_provider.add_span_processor(BaggageSpanProcessor(self.matches_regex))

        # tracer has no baggage to start
        tracer = tracer_provider.get_tracer("my-tracer")
        self.assertIsInstance(tracer, Tracer)
        self.assertEqual(get_all_baggage(), {})
        # set baggage in context
        ctx = set_baggage("queen", "bee")
        with tracer.start_as_current_span(name="bumble", context=ctx) as bumble_span:
            # span should have baggage key-value pair in context
            self.assertEqual(get_all_baggage(ctx), {"queen": "bee"})
            # span should have baggage key-value pair in attribute
            self.assertEqual(bumble_span._attributes["queen"], "bee")
            with tracer.start_as_current_span(name="child_span", context=ctx) as child_span:
                self.assertIsInstance(child_span, Span)
                # child span should have baggage key-value pair in context
                self.assertEqual(get_all_baggage(ctx), {"queen": "bee"})
                # child span should have baggage key-value pair in attribute
                self.assertEqual(child_span._attributes["queen"], "bee")

    def test_set_baggage_attaches_to_child_spans_and_detaches_properly_with_token(
        self,
    ):
        tracer_provider = TracerProvider()
        tracer_provider.add_span_processor(BaggageSpanProcessor(ALLOW_ALL_BAGGAGE_KEYS))

        # tracer has no baggage to start
        tracer = tracer_provider.get_tracer("my-tracer")
        self.assertIsInstance(tracer, Tracer)
        self.assertEqual(get_all_baggage(), {})
        # create a context token and set baggage
        honey_token = attach(set_baggage("bumble", "bee"))
        self.assertEqual(get_all_baggage(), {"bumble": "bee"})
        # in a new span, ensure the baggage is there
        with tracer.start_as_current_span("parent") as span:
            self.assertEqual(get_all_baggage(), {"bumble": "bee"})
            self.assertEqual(span._attributes["bumble"], "bee")
            # create a second context token and set more baggage
            moar_token = attach(set_baggage("moar", "bee"))
            self.assertEqual(get_all_baggage(), {"bumble": "bee", "moar": "bee"})
            # in a child span, ensure all baggage is there as attributes
            with tracer.start_as_current_span("child") as child_span:
                self.assertEqual(get_all_baggage(), {"bumble": "bee", "moar": "bee"})
                self.assertEqual(child_span._attributes["bumble"], "bee")
                self.assertEqual(child_span._attributes["moar"], "bee")
            detach(moar_token)
        detach(honey_token)
        self.assertEqual(get_all_baggage(), {})

    @staticmethod
    def has_prefix(baggage_key: str) -> bool:
        return baggage_key.startswith("que")

    @staticmethod
    def matches_regex(baggage_key: str) -> bool:
        return re.match(r"que.*", baggage_key) is not None


class BaggageSpanProcessorIncludeExcludeTest(unittest.TestCase):
    @staticmethod
    def _span_attributes(processor, baggage_keys):
        tracer_provider = TracerProvider()
        tracer_provider.add_span_processor(processor)
        tracer = tracer_provider.get_tracer("my-tracer")
        with tracer.start_as_current_span("span", context=_baggage_context(baggage_keys)) as span:
            return dict(span.attributes)

    def test_include_exclude(self):
        for included, excluded, baggage_keys, expected in _INCLUDE_EXCLUDE_CASES:
            with self.subTest(included=included, excluded=excluded):
                attributes = self._span_attributes(
                    BaggageSpanProcessor(included=included, excluded=excluded),
                    baggage_keys,
                )
                self.assertEqual(attributes, dict.fromkeys(expected, "value"))

    def test_no_arguments_copies_all_baggage(self):
        attributes = self._span_attributes(BaggageSpanProcessor(), ["a", "b"])
        self.assertEqual(attributes, {"a": "value", "b": "value"})

    def test_predicate_with_include_exclude_raises(self):
        for kwargs in ({"included": ["a"]}, {"excluded": ["a"]}, {"included": []}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    BaggageSpanProcessor(ALLOW_ALL_BAGGAGE_KEYS, **kwargs)

    def test_entry_point(self):
        (entry_point,) = entry_points(group="opentelemetry_traces_processor", name="baggage")
        processor_class = entry_point.load()
        self.assertIs(processor_class, BaggageSpanProcessor)
        attributes = self._span_attributes(
            processor_class(included=["a*"], excluded=["ab"]),
            ["a", "ab", "b"],
        )
        self.assertEqual(attributes, {"a": "value"})
