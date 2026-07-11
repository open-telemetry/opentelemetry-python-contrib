# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from unittest import TestCase

from opentelemetry.sampler.jaeger.remote._samplers import (
    GuaranteedThroughputSampler,
    PerOperationSampler,
    ProbabilisticSampler,
    RateLimitingSampler,
)
from opentelemetry.sdk.trace.sampling import Decision, TraceIdRatioBased

_TRACE_IDS = [1, 2, 3, 12345, 2**63, 2**64 - 1]


class _FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


class TestProbabilisticSampler(TestCase):
    def test_rate_one_always_samples(self):
        sampler = ProbabilisticSampler(1.0)
        for trace_id in _TRACE_IDS:
            result = sampler.should_sample(None, trace_id, "span")
            self.assertEqual(result.decision, Decision.RECORD_AND_SAMPLE)

    def test_rate_zero_never_samples(self):
        sampler = ProbabilisticSampler(0.0)
        for trace_id in _TRACE_IDS:
            result = sampler.should_sample(None, trace_id, "span")
            self.assertEqual(result.decision, Decision.DROP)

    def test_matches_trace_id_ratio_based(self):
        rate = 0.3
        sampler = ProbabilisticSampler(rate)
        reference = TraceIdRatioBased(rate)
        for trace_id in _TRACE_IDS:
            self.assertEqual(
                sampler.should_sample(None, trace_id, "span").decision,
                reference.should_sample(None, trace_id, "span").decision,
            )

    def test_rejects_out_of_range_rate(self):
        for rate in (-0.1, 1.1):
            with self.subTest(rate=rate):
                with self.assertRaises(ValueError):
                    ProbabilisticSampler(rate)

    def test_attributes_include_sampler_tags(self):
        attributes = {"foo": "bar"}
        for rate in (1.0, 0.0):
            with self.subTest(rate=rate):
                sampler = ProbabilisticSampler(rate)
                result = sampler.should_sample(
                    None, _TRACE_IDS[0], "span", attributes=attributes
                )
                self.assertEqual(
                    dict(result.attributes),
                    {
                        "foo": "bar",
                        "sampler.type": "probabilistic",
                        "sampler.param": rate,
                    },
                )

    def test_get_description(self):
        sampler = ProbabilisticSampler(0.5)
        self.assertEqual(
            sampler.get_description(), "ProbabilisticSampler{0.5}"
        )

    def test_rate_property(self):
        sampler = ProbabilisticSampler(0.5)
        self.assertEqual(sampler.rate, 0.5)

    def test_update_reconfigures_in_place(self):
        sampler = ProbabilisticSampler(0.0)
        result = sampler.should_sample(None, _TRACE_IDS[0], "span")
        self.assertEqual(result.decision, Decision.DROP)

        sampler.update(1.0)

        self.assertEqual(sampler.rate, 1.0)
        self.assertEqual(
            sampler.get_description(), "ProbabilisticSampler{1.0}"
        )
        result = sampler.should_sample(None, _TRACE_IDS[0], "span")
        self.assertEqual(result.decision, Decision.RECORD_AND_SAMPLE)

    def test_update_rejects_out_of_range_rate(self):
        sampler = ProbabilisticSampler(1.0)

        with self.assertRaises(ValueError):
            sampler.update(2.0)

        self.assertEqual(sampler.rate, 1.0)
        result = sampler.should_sample(None, _TRACE_IDS[0], "span")
        self.assertEqual(result.decision, Decision.RECORD_AND_SAMPLE)


class TestRateLimitingSampler(TestCase):
    def test_samples_first_n_then_drops(self):
        clock = _FakeClock()
        sampler = RateLimitingSampler(3, clock=clock)

        for _ in range(3):
            result = sampler.should_sample(None, _TRACE_IDS[0], "span")
            self.assertEqual(result.decision, Decision.RECORD_AND_SAMPLE)

        result = sampler.should_sample(None, _TRACE_IDS[0], "span")
        self.assertEqual(result.decision, Decision.DROP)

    def test_refill_over_time(self):
        clock = _FakeClock()
        sampler = RateLimitingSampler(10, clock=clock)

        for _ in range(10):
            sampler.should_sample(None, _TRACE_IDS[0], "span")
        self.assertEqual(
            sampler.should_sample(None, _TRACE_IDS[0], "span").decision,
            Decision.DROP,
        )

        clock.advance(0.5)
        sampled = 0
        for _ in range(10):
            if (
                sampler.should_sample(None, _TRACE_IDS[0], "span").decision
                == Decision.RECORD_AND_SAMPLE
            ):
                sampled += 1
        self.assertEqual(sampled, 5)

    def test_sub_one_rate(self):
        clock = _FakeClock()
        sampler = RateLimitingSampler(0.5, clock=clock)

        result = sampler.should_sample(None, _TRACE_IDS[0], "span")
        self.assertEqual(result.decision, Decision.RECORD_AND_SAMPLE)
        result = sampler.should_sample(None, _TRACE_IDS[0], "span")
        self.assertEqual(result.decision, Decision.DROP)

    def test_attributes_include_sampler_tags(self):
        clock = _FakeClock()
        attributes = {"foo": "bar"}
        sampler = RateLimitingSampler(1, clock=clock)
        expected_attributes = {
            "foo": "bar",
            "sampler.type": "ratelimiting",
            "sampler.param": 1,
        }

        result = sampler.should_sample(
            None, _TRACE_IDS[0], "span", attributes=attributes
        )
        self.assertEqual(result.decision, Decision.RECORD_AND_SAMPLE)
        self.assertEqual(dict(result.attributes), expected_attributes)

        result = sampler.should_sample(
            None, _TRACE_IDS[0], "span", attributes=attributes
        )
        self.assertEqual(result.decision, Decision.DROP)
        self.assertEqual(dict(result.attributes), expected_attributes)

    def test_get_description(self):
        sampler = RateLimitingSampler(2)
        self.assertEqual(sampler.get_description(), "RateLimitingSampler{2}")

    def test_max_traces_per_second_property(self):
        sampler = RateLimitingSampler(2)
        self.assertEqual(sampler.max_traces_per_second, 2)

    def test_update_reconfigures_in_place(self):
        clock = _FakeClock()

        sampler = RateLimitingSampler(1, clock=clock)

        sampler.update(5)

        self.assertEqual(sampler.max_traces_per_second, 5)
        self.assertEqual(sampler.get_description(), "RateLimitingSampler{5}")

        sampled = 0
        for _ in range(10):
            if (
                sampler.should_sample(None, _TRACE_IDS[0], "span").decision
                == Decision.RECORD_AND_SAMPLE
            ):
                sampled += 1
        self.assertEqual(sampled, 5)


class TestGuaranteedThroughputSampler(TestCase):
    def test_probabilistic_win_spends_lower_bound_credit(self):
        clock = _FakeClock()
        sampler = GuaranteedThroughputSampler(1.0, 1.0, clock=clock)

        result = sampler.should_sample(None, _TRACE_IDS[0], "op")
        self.assertEqual(result.decision, Decision.RECORD_AND_SAMPLE)
        self.assertEqual(
            dict(result.attributes),
            {"sampler.type": "probabilistic", "sampler.param": 1.0},
        )

        sampler.update(0.0, 1.0)
        result = sampler.should_sample(None, _TRACE_IDS[0], "op")
        self.assertEqual(result.decision, Decision.DROP)
        self.assertEqual(
            dict(result.attributes),
            {"sampler.type": "lowerbound", "sampler.param": 1.0},
        )

    def test_lower_bound_guarantees_on_drop(self):
        clock = _FakeClock()
        sampler = GuaranteedThroughputSampler(0.0, 2.0, clock=clock)

        for _ in range(2):
            result = sampler.should_sample(None, _TRACE_IDS[0], "op")
            self.assertEqual(result.decision, Decision.RECORD_AND_SAMPLE)
            self.assertEqual(
                dict(result.attributes),
                {"sampler.type": "lowerbound", "sampler.param": 2.0},
            )

        result = sampler.should_sample(None, _TRACE_IDS[0], "op")
        self.assertEqual(result.decision, Decision.DROP)
        self.assertEqual(
            dict(result.attributes),
            {"sampler.type": "lowerbound", "sampler.param": 2.0},
        )

    def test_attributes_include_sampler_tags_on_lower_bound_path(self):
        clock = _FakeClock()
        sampler = GuaranteedThroughputSampler(0.0, 2.0, clock=clock)
        attributes = {"foo": "bar"}

        result = sampler.should_sample(
            None, _TRACE_IDS[0], "op", attributes=attributes
        )
        self.assertEqual(result.decision, Decision.RECORD_AND_SAMPLE)
        self.assertEqual(
            dict(result.attributes),
            {
                "foo": "bar",
                "sampler.type": "lowerbound",
                "sampler.param": 2.0,
            },
        )

    def test_lower_bound_zero_disables_guarantee(self):
        clock = _FakeClock()
        sampler = GuaranteedThroughputSampler(0.0, 0.0, clock=clock)

        for _ in range(5):
            result = sampler.should_sample(None, _TRACE_IDS[0], "op")
            self.assertEqual(result.decision, Decision.DROP)

    def test_update_toggles_limiter(self):
        clock = _FakeClock()
        sampler = GuaranteedThroughputSampler(0.0, 0.0, clock=clock)
        self.assertEqual(
            sampler.should_sample(None, _TRACE_IDS[0], "op").decision,
            Decision.DROP,
        )

        sampler.update(0.0, 3.0)
        sampled = 0
        for _ in range(5):
            if (
                sampler.should_sample(None, _TRACE_IDS[0], "op").decision
                == Decision.RECORD_AND_SAMPLE
            ):
                sampled += 1
        self.assertEqual(sampled, 3)

        sampler.update(0.0, 0.0)
        self.assertEqual(
            sampler.should_sample(None, _TRACE_IDS[0], "op").decision,
            Decision.DROP,
        )


class TestPerOperationSampler(TestCase):
    def test_known_operation_uses_specific_rate(self):
        sampler = PerOperationSampler(
            default_sampling_probability=0.0,
            default_lower_bound_traces_per_second=0.0,
            per_operation_strategies=[("op-a", 1.0)],
        )

        result = sampler.should_sample(None, _TRACE_IDS[0], "op-a")
        self.assertEqual(result.decision, Decision.RECORD_AND_SAMPLE)

        result = sampler.should_sample(None, _TRACE_IDS[0], "op-b")
        self.assertEqual(result.decision, Decision.DROP)

    def test_over_cap_falls_back_to_default(self):
        sampler = PerOperationSampler(
            default_sampling_probability=1.0,
            default_lower_bound_traces_per_second=0.0,
            per_operation_strategies=[("op-a", 0.0)],
            max_operations=1,
        )

        result = sampler.should_sample(None, _TRACE_IDS[0], "op-a")
        self.assertEqual(result.decision, Decision.DROP)

        result = sampler.should_sample(None, _TRACE_IDS[0], "op-b")
        self.assertEqual(result.decision, Decision.RECORD_AND_SAMPLE)
        self.assertNotIn("op-b", sampler._operation_samplers)

    def test_update_prunes_absent_operations(self):
        sampler = PerOperationSampler(
            default_sampling_probability=1.0,
            default_lower_bound_traces_per_second=0.0,
            per_operation_strategies=[("op-a", 0.0), ("op-b", 0.0)],
        )
        self.assertEqual(
            sampler.should_sample(None, _TRACE_IDS[0], "op-a").decision,
            Decision.DROP,
        )

        sampler.update(
            default_sampling_probability=1.0,
            default_lower_bound_traces_per_second=0.0,
            per_operation_strategies=[("op-a", 1.0)],
        )

        self.assertEqual(
            sampler.should_sample(None, _TRACE_IDS[0], "op-a").decision,
            Decision.RECORD_AND_SAMPLE,
        )

        self.assertNotIn("op-b", sampler._operation_samplers)
        self.assertEqual(
            sampler.should_sample(None, _TRACE_IDS[0], "op-b").decision,
            Decision.RECORD_AND_SAMPLE,
        )

    def test_update_preserves_balance_for_retained_ops(
        self,
    ):
        clock = _FakeClock()
        sampler = PerOperationSampler(
            default_sampling_probability=0.0,
            default_lower_bound_traces_per_second=0.0,
            per_operation_strategies=[("op-a", 0.0)],
            clock=clock,
        )
        sampler.update(
            default_sampling_probability=0.0,
            default_lower_bound_traces_per_second=1.0,
            per_operation_strategies=[("op-a", 0.0)],
        )
        self.assertEqual(
            sampler.should_sample(None, _TRACE_IDS[0], "op-a").decision,
            Decision.RECORD_AND_SAMPLE,
        )
        existing_sampler = sampler._operation_samplers["op-a"]

        sampler.update(
            default_sampling_probability=0.0,
            default_lower_bound_traces_per_second=1.0,
            per_operation_strategies=[("op-a", 0.0)],
        )
        self.assertIs(sampler._operation_samplers["op-a"], existing_sampler)
        self.assertEqual(
            sampler.should_sample(None, _TRACE_IDS[0], "op-a").decision,
            Decision.DROP,
        )

    def test_get_description(self):
        sampler = PerOperationSampler(
            default_sampling_probability=0.5,
            default_lower_bound_traces_per_second=0.0,
            per_operation_strategies=[("op-a", 1.0)],
        )
        description = sampler.get_description()
        self.assertIn("PerOperationSampler{", description)
        self.assertIn("op-a", description)
