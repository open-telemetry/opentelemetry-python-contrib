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
