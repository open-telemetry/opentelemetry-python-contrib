# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest
from google.cloud.aiplatform_v1.services.prediction_service import client
from google.cloud.aiplatform_v1beta1.services.prediction_service import (
    client as client_v1beta1,
)

from opentelemetry.instrumentation.vertexai import VertexAIInstrumentor


@pytest.fixture(
    name="client_class",
    params=[
        pytest.param(client.PredictionServiceClient, id="v1"),
        pytest.param(client_v1beta1.PredictionServiceClient, id="v1beta1"),
    ],
)
def fixture_client_class(request: pytest.FixtureRequest):
    return request.param


def test_instruments(
    instrument_with_content: VertexAIInstrumentor, client_class
):
    assert hasattr(client_class.generate_content, "__wrapped__")


def test_uninstruments(
    instrument_with_content: VertexAIInstrumentor, client_class
):
    instrument_with_content.uninstrument()
    assert not hasattr(client_class.generate_content, "__wrapped__")
