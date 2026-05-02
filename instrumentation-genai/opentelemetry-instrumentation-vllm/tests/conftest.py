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

"""Shared fixtures for vLLM instrumentation tests."""

import sys
import types
from unittest.mock import MagicMock

import pytest

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)


def _build_mock_request_output(
    request_id="req-001",
    prompt_token_ids=None,
    output_text="Hello!",
    output_token_ids=None,
    finish_reason="stop",
    model=None,
    ttft=None,
    tpot=None,
):
    """Build a mock vLLM RequestOutput."""
    if prompt_token_ids is None:
        prompt_token_ids = list(range(10))
    if output_token_ids is None:
        output_token_ids = list(range(5))

    output = MagicMock()
    output.text = output_text
    output.token_ids = output_token_ids
    output.finish_reason = finish_reason

    metrics = MagicMock()
    metrics.first_token_latency = ttft
    metrics.mean_time_per_output_token = tpot

    result = MagicMock()
    result.request_id = request_id
    result.prompt_token_ids = prompt_token_ids
    result.outputs = [output]
    result.metrics = metrics
    result.model = model

    return result


def _install_mock_vllm():
    """Install a mock vllm module into sys.modules so wrapt can resolve it."""
    mock_vllm = types.ModuleType("vllm")
    mock_vllm.__version__ = "0.8.0"

    class MockLLM:
        def __init__(self, model="test-model", **kwargs):
            self.model = model
            self._fail_with = None
            engine = MagicMock()
            engine.model_config.model = model
            self.llm_engine = engine

        def generate(self, prompts, sampling_params=None, **kwargs):
            if self._fail_with:
                raise self._fail_with
            return [
                _build_mock_request_output(
                    model=self.model,
                    ttft=0.05,
                    tpot=0.01,
                )
            ]

        def chat(self, messages, sampling_params=None, **kwargs):
            if self._fail_with:
                raise self._fail_with
            return [
                _build_mock_request_output(
                    model=self.model,
                    ttft=0.03,
                    tpot=0.008,
                )
            ]

    mock_vllm.LLM = MockLLM
    sys.modules["vllm"] = mock_vllm
    return mock_vllm, MockLLM


# Install mock before any import of the instrumentor
_mock_vllm, MockLLM = _install_mock_vllm()


@pytest.fixture(scope="function")
def span_exporter():
    exporter = InMemorySpanExporter()
    yield exporter


@pytest.fixture(scope="function")
def metric_reader():
    reader = InMemoryMetricReader()
    yield reader


@pytest.fixture(scope="function")
def tracer_provider(span_exporter):
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    return provider


@pytest.fixture(scope="function")
def meter_provider(metric_reader):
    return MeterProvider(metric_readers=[metric_reader])


@pytest.fixture(scope="function")
def instrument(tracer_provider, meter_provider):
    from opentelemetry.instrumentation.vllm import VLLMInstrumentor

    instrumentor = VLLMInstrumentor()
    instrumentor.instrument(
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
        skip_dep_check=True,
    )
    yield instrumentor
    instrumentor.uninstrument()


@pytest.fixture
def mock_llm():
    """Return a fresh MockLLM instance."""
    return MockLLM(model="meta-llama/Llama-2-7b-hf")
