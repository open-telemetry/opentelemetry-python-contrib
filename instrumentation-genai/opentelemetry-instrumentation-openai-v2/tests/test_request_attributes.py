# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for get_llm_request_attributes and span name logic in utils.py."""

from types import SimpleNamespace

import pytest

from opentelemetry.instrumentation.openai_v2.patch import (
    _get_embeddings_span_name,
)
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


def test_model_omitted_when_missing():
    """When 'model' is not in kwargs, GEN_AI_REQUEST_MODEL should be absent."""
    attrs = get_llm_request_attributes(
        kwargs={},
        client_instance=_make_client(),
        latest_experimental_enabled=False,
    )
    assert GenAIAttributes.GEN_AI_REQUEST_MODEL not in attrs


def test_model_omitted_when_missing_experimental():
    """Same as above but with latest_experimental_enabled=True."""
    attrs = get_llm_request_attributes(
        kwargs={},
        client_instance=_make_client(),
        latest_experimental_enabled=True,
    )
    assert GenAIAttributes.GEN_AI_REQUEST_MODEL not in attrs


def test_model_preserved_when_provided():
    """When 'model' is in kwargs, GEN_AI_REQUEST_MODEL should be set to its value."""
    attrs = get_llm_request_attributes(
        kwargs={"model": "gpt-4o-mini"},
        client_instance=_make_client(),
        latest_experimental_enabled=False,
    )
    assert attrs[GenAIAttributes.GEN_AI_REQUEST_MODEL] == "gpt-4o-mini"


def test_span_name_includes_model_when_present():
    """Span name should be '{operation} {model}' when model is provided."""
    attrs = get_llm_request_attributes(
        kwargs={"model": "gpt-4o"},
        client_instance=_make_client(),
        latest_experimental_enabled=False,
    )
    operation_name = attrs[GenAIAttributes.GEN_AI_OPERATION_NAME]
    model = attrs.get(GenAIAttributes.GEN_AI_REQUEST_MODEL)
    span_name = f"{operation_name} {model}" if model else operation_name
    assert span_name == "chat gpt-4o"


def test_span_name_uses_operation_only_when_model_missing():
    """Span name should be just '{operation}' when model is not provided."""
    attrs = get_llm_request_attributes(
        kwargs={},
        client_instance=_make_client(),
        latest_experimental_enabled=False,
    )
    operation_name = attrs[GenAIAttributes.GEN_AI_OPERATION_NAME]
    model = attrs.get(GenAIAttributes.GEN_AI_REQUEST_MODEL)
    span_name = f"{operation_name} {model}" if model else operation_name
    assert span_name == "chat"


def test_embeddings_span_name_includes_model():
    """Embeddings span name should be '{operation} {model}' when model is present."""
    span_attributes = {
        GenAIAttributes.GEN_AI_OPERATION_NAME: "embeddings",
        GenAIAttributes.GEN_AI_REQUEST_MODEL: "text-embedding-3-small",
    }
    assert (
        _get_embeddings_span_name(span_attributes)
        == "embeddings text-embedding-3-small"
    )


def test_embeddings_span_name_without_model():
    """Embeddings span name should be just '{operation}' when model is absent."""
    span_attributes = {
        GenAIAttributes.GEN_AI_OPERATION_NAME: "embeddings",
    }
    assert _get_embeddings_span_name(span_attributes) == "embeddings"
