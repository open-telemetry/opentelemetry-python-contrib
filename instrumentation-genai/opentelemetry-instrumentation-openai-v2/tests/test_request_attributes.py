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

"""Unit tests for get_llm_request_attributes in utils.py."""

from types import SimpleNamespace

import pytest

from opentelemetry.instrumentation.openai_v2.utils import (
    get_llm_request_attributes,
)
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)


@pytest.fixture(autouse=True)
def fixture_vcr():
    """No VCR needed for these unit tests."""
    yield


def _make_client(base_url=None):
    return SimpleNamespace(_base_url=base_url)


def test_model_defaults_to_empty_string_when_missing():
    """When 'model' is not in kwargs, GEN_AI_REQUEST_MODEL should be empty string."""
    attrs = get_llm_request_attributes(
        kwargs={},
        client_instance=_make_client(),
        latest_experimental_enabled=False,
    )
    assert GenAIAttributes.GEN_AI_REQUEST_MODEL in attrs
    assert attrs[GenAIAttributes.GEN_AI_REQUEST_MODEL] == ""


def test_model_defaults_to_empty_string_when_missing_experimental():
    """Same as above but with latest_experimental_enabled=True."""
    attrs = get_llm_request_attributes(
        kwargs={},
        client_instance=_make_client(),
        latest_experimental_enabled=True,
    )
    assert GenAIAttributes.GEN_AI_REQUEST_MODEL in attrs
    assert attrs[GenAIAttributes.GEN_AI_REQUEST_MODEL] == ""


def test_model_preserved_when_provided():
    """When 'model' is in kwargs, GEN_AI_REQUEST_MODEL should be set to its value."""
    attrs = get_llm_request_attributes(
        kwargs={"model": "gpt-4o-mini"},
        client_instance=_make_client(),
        latest_experimental_enabled=False,
    )
    assert attrs[GenAIAttributes.GEN_AI_REQUEST_MODEL] == "gpt-4o-mini"
