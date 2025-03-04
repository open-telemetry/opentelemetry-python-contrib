import pytest
from google.cloud.aiplatform_v1.services.prediction_service import client
from google.cloud.aiplatform_v1beta1.services.prediction_service import (
    client as client_v1beta1,
)

from opentelemetry.instrumentation.vertexai import VertexAIInstrumentor


@pytest.fixture(name="instrumentor")
def fixture_instrumentor():
    instrumentor = VertexAIInstrumentor()
    instrumentor.instrument()
    yield instrumentor

    if instrumentor.is_instrumented_by_opentelemetry:
        instrumentor.uninstrument()


@pytest.fixture(
    name="client_class",
    params=[
        pytest.param(client.PredictionServiceClient, id="v1"),
        pytest.param(client_v1beta1.PredictionServiceClient, id="v1beta1"),
    ],
)
def fixture_client_class(request):
    return request.param


def test_instruments(instrumentor: VertexAIInstrumentor, client_class):
    assert hasattr(client_class.generate_content, "__wrapped__")


def test_uninstruments(instrumentor: VertexAIInstrumentor, client_class):
    instrumentor.uninstrument()
    assert not hasattr(client_class.generate_content, "__wrapped__")
