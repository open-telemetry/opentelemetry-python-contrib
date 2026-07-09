# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Provider (``gen_ai.provider.name``) resolution tests.

LiteLLM uses provider prefixes (``azure``, ``bedrock``, ``vertex_ai``, ...)
that differ from the OTel ``gen_ai.provider.name`` well-known values. These
assert the instrumentation normalizes them to the upstream values, while
unknown providers pass through unchanged and bare models fall back to the
litellm-specific literal.
"""

from __future__ import annotations

import pytest

from opentelemetry.instrumentation.litellm.utils import (
    resolve_provider_from_kwargs,
    resolve_provider_from_response,
)
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)

_Provider = GenAIAttributes.GenAiProviderNameValues


@pytest.mark.parametrize(
    "model,expected",
    [
        ("azure/gpt-4o", _Provider.AZURE_AI_OPENAI.value),
        ("azure_ai/grok-3", _Provider.AZURE_AI_INFERENCE.value),
        ("bedrock/anthropic.claude-3", _Provider.AWS_BEDROCK.value),
        ("vertex_ai/gemini-1.5-pro", _Provider.GCP_VERTEX_AI.value),
        ("gemini/gemini-1.5-pro", _Provider.GCP_GEMINI.value),
        ("mistral/mistral-large", _Provider.MISTRAL_AI.value),
        # OpenAI already matches the published value; unknown pass through.
        ("openai/gpt-4o", "openai"),
        ("someprovider/some-model", "someprovider"),
    ],
)
def test_provider_resolution_normalizes_aliases(model, expected):
    assert resolve_provider_from_kwargs({"model": model}) == expected


def test_explicit_custom_llm_provider_is_normalized():
    assert (
        resolve_provider_from_kwargs(
            {"model": "x", "custom_llm_provider": "bedrock"}
        )
        == _Provider.AWS_BEDROCK.value
    )


def test_bare_model_falls_back_to_litellm():
    assert (
        resolve_provider_from_kwargs({"model": "gpt-3.5-turbo"}) == "litellm"
    )


def test_positional_model_resolves_provider():
    # litellm.completion("bedrock/claude-3", messages=...) passes the model
    # positionally; provider must still resolve from the prefix.
    assert (
        resolve_provider_from_kwargs({}, ("bedrock/anthropic.claude-3",))
        == _Provider.AWS_BEDROCK.value
    )


def test_resolve_from_response_hidden_params():
    class _Resp:
        _hidden_params = {"custom_llm_provider": "bedrock"}

    assert (
        resolve_provider_from_response(_Resp()) == _Provider.AWS_BEDROCK.value
    )


def test_resolve_from_response_missing_returns_none():
    class _Resp:
        _hidden_params = {}

    assert resolve_provider_from_response(_Resp()) is None
