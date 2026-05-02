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

"""Tests for the CohereInstrumentor class."""

from opentelemetry.instrumentation.cohere import CohereInstrumentor


def test_instrumentor_instantiation():
    instrumentor = CohereInstrumentor()
    assert instrumentor is not None
    assert isinstance(instrumentor, CohereInstrumentor)


def test_instrumentation_dependencies():
    instrumentor = CohereInstrumentor()
    dependencies = instrumentor.instrumentation_dependencies()

    assert dependencies is not None
    assert len(dependencies) > 0
    assert "cohere >= 5.0.0" in dependencies


def test_instrument_uninstrument_cycle(
    tracer_provider, logger_provider, meter_provider
):
    instrumentor = CohereInstrumentor()

    instrumentor.instrument(
        tracer_provider=tracer_provider,
        logger_provider=logger_provider,
        meter_provider=meter_provider,
    )
    instrumentor.uninstrument()

    instrumentor.instrument(
        tracer_provider=tracer_provider,
        logger_provider=logger_provider,
        meter_provider=meter_provider,
    )
    instrumentor.uninstrument()


def test_uninstrument_without_instrument():
    instrumentor = CohereInstrumentor()
    instrumentor.uninstrument()


def test_instrumentor_has_required_attributes():
    instrumentor = CohereInstrumentor()

    assert hasattr(instrumentor, "instrument")
    assert hasattr(instrumentor, "uninstrument")
    assert hasattr(instrumentor, "instrumentation_dependencies")
    assert callable(instrumentor.instrument)
    assert callable(instrumentor.uninstrument)
    assert callable(instrumentor.instrumentation_dependencies)
