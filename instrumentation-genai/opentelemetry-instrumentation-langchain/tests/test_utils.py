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

import pytest

from opentelemetry.instrumentation.langchain.utils import (
    infer_provider_name,
    infer_server_address,
    infer_server_port,
)

# ---------------------------------------------------------------------------
# infer_provider_name
# ---------------------------------------------------------------------------


class TestInferProviderNameFromMetadata:
    """Provider resolution via metadata ls_provider field."""

    @pytest.mark.parametrize(
        "ls_provider, expected",
        [
            ("openai", "openai"),
            ("anthropic", "anthropic"),
            ("cohere", "cohere"),
            ("ollama", "ollama"),
        ],
    )
    def test_direct_mapping(self, ls_provider, expected):
        metadata = {"ls_provider": ls_provider}
        assert infer_provider_name({}, metadata, {}) == expected

    @pytest.mark.parametrize(
        "ls_provider",
        ["azure", "azure_openai"],
    )
    def test_azure_variants(self, ls_provider):
        metadata = {"ls_provider": ls_provider}
        assert infer_provider_name({}, metadata, {}) == "azure.ai.openai"

    def test_github_maps_to_azure(self):
        metadata = {"ls_provider": "github"}
        assert infer_provider_name({}, metadata, {}) == "azure.ai.openai"

    @pytest.mark.parametrize(
        "ls_provider",
        ["amazon_bedrock", "bedrock", "aws_bedrock"],
    )
    def test_bedrock_variants(self, ls_provider):
        metadata = {"ls_provider": ls_provider}
        assert infer_provider_name({}, metadata, {}) == "aws.bedrock"

    def test_google(self):
        metadata = {"ls_provider": "google"}
        assert infer_provider_name({}, metadata, {}) == "gcp.gen_ai"


class TestInferProviderNameFromBaseUrl:
    """Provider resolution via base_url in invocation_params."""

    @pytest.mark.parametrize(
        "url, expected",
        [
            ("https://my-resource.openai.azure.com/v1", "azure.ai.openai"),
            ("https://api.openai.com/v1", "openai"),
            (
                "https://bedrock-runtime.us-east-1.amazonaws.com",
                "aws.bedrock",
            ),
            ("https://api.anthropic.com/v1", "anthropic"),
            (
                "https://us-central1-aiplatform.googleapis.com",
                "gcp.gen_ai",
            ),
        ],
    )
    def test_url_patterns(self, url, expected):
        invocation_params = {"base_url": url}
        assert infer_provider_name({}, {}, invocation_params) == expected

    def test_azure_keyword_in_url(self):
        invocation_params = {
            "base_url": "https://custom-azure-endpoint.example.com/v1"
        }
        assert (
            infer_provider_name({}, {}, invocation_params) == "azure.ai.openai"
        )

    def test_ollama_keyword_in_url(self):
        invocation_params = {
            "base_url": "https://my-ollama-server.local:11434/api"
        }
        assert infer_provider_name({}, {}, invocation_params) == "ollama"

    def test_amazonaws_in_url(self):
        invocation_params = {
            "base_url": "https://runtime.sagemaker.us-west-2.amazonaws.com"
        }
        assert infer_provider_name({}, {}, invocation_params) == "aws.bedrock"

    def test_openai_com_in_url(self):
        invocation_params = {"base_url": "https://api.openai.com/v2/chat"}
        assert infer_provider_name({}, {}, invocation_params) == "openai"


class TestInferProviderNameFromSerializedClassName:
    """Provider resolution via serialized name/id fields."""

    @pytest.mark.parametrize(
        "class_name, expected",
        [
            ("ChatOpenAI", "openai"),
            ("ChatBedrock", "aws.bedrock"),
            ("ChatAnthropic", "anthropic"),
            ("ChatGoogleGenerativeAI", "gcp.gen_ai"),
        ],
    )
    def test_class_name(self, class_name, expected):
        serialized = {"name": class_name}
        assert infer_provider_name(serialized, {}, {}) == expected

    @pytest.mark.parametrize(
        "class_name, expected",
        [
            ("ChatOpenAI", "openai"),
            ("ChatBedrock", "aws.bedrock"),
            ("ChatAnthropic", "anthropic"),
            ("ChatGoogleGenerativeAI", "gcp.gen_ai"),
        ],
    )
    def test_class_name_via_id(self, class_name, expected):
        serialized = {"id": ["langchain_openai", "chat_models", class_name]}
        assert infer_provider_name(serialized, {}, {}) == expected


class TestInferProviderNameFromSerializedKwargs:
    """Provider resolution via kwargs in serialized dict."""

    def test_azure_endpoint_kwarg(self):
        serialized = {
            "kwargs": {"azure_endpoint": "https://my-model.openai.azure.com/"}
        }
        assert infer_provider_name(serialized, {}, {}) == "azure.ai.openai"


class TestInferProviderNameReturnsNone:
    """Returns None when no provider signals are available."""

    def test_empty_inputs(self):
        assert infer_provider_name({}, {}, {}) is None

    def test_none_inputs(self):
        assert infer_provider_name({}, None, None) is None

    def test_unrecognized_metadata(self):
        metadata = {"ls_provider": "some_unknown_provider"}
        assert infer_provider_name({}, metadata, {}) is None

    def test_unrecognized_url(self):
        invocation_params = {"base_url": "https://custom-llm.example.com/v1"}
        assert infer_provider_name({}, {}, invocation_params) is None

    def test_unrecognized_class_name(self):
        serialized = {"name": "ChatCustomLLM"}
        assert infer_provider_name(serialized, {}, {}) is None


class TestInferProviderNamePriority:
    """Metadata takes priority over invocation_params over serialized."""

    def test_metadata_over_invocation_params(self):
        metadata = {"ls_provider": "anthropic"}
        invocation_params = {"base_url": "https://api.openai.com/v1"}
        assert (
            infer_provider_name({}, metadata, invocation_params) == "anthropic"
        )

    def test_metadata_over_serialized(self):
        metadata = {"ls_provider": "anthropic"}
        serialized = {"name": "ChatOpenAI"}
        assert infer_provider_name(serialized, metadata, {}) == "anthropic"

    def test_invocation_params_over_serialized(self):
        invocation_params = {"base_url": "https://api.anthropic.com/v1"}
        serialized = {"name": "ChatOpenAI"}
        assert (
            infer_provider_name(serialized, {}, invocation_params)
            == "anthropic"
        )


# ---------------------------------------------------------------------------
# infer_server_address
# ---------------------------------------------------------------------------


class TestInferServerAddress:
    """Extract hostname from various URL sources."""

    def test_from_invocation_params_base_url(self):
        invocation_params = {"base_url": "https://api.openai.com/v1"}
        assert infer_server_address({}, invocation_params) == "api.openai.com"

    def test_from_serialized_openai_api_base(self):
        serialized = {
            "kwargs": {"openai_api_base": "https://my-model.openai.azure.com/"}
        }
        assert (
            infer_server_address(serialized, {}) == "my-model.openai.azure.com"
        )

    def test_from_serialized_azure_endpoint(self):
        serialized = {
            "kwargs": {
                "azure_endpoint": "https://my-resource.openai.azure.com/"
            }
        }
        assert (
            infer_server_address(serialized, {})
            == "my-resource.openai.azure.com"
        )

    def test_returns_none_when_no_url(self):
        assert infer_server_address({}, {}) is None

    def test_returns_none_for_empty_inputs(self):
        assert infer_server_address({}, None) is None

    def test_returns_none_for_none_serialized_kwargs(self):
        serialized = {"kwargs": {}}
        assert infer_server_address(serialized, {}) is None

    def test_strips_port_from_hostname(self):
        invocation_params = {"base_url": "http://localhost:11434/v1"}
        assert infer_server_address({}, invocation_params) == "localhost"

    def test_handles_url_with_path(self):
        invocation_params = {
            "base_url": "https://api.openai.com/v1/chat/completions"
        }
        assert infer_server_address({}, invocation_params) == "api.openai.com"

    def test_handles_malformed_url(self):
        invocation_params = {"base_url": "not-a-valid-url"}
        result = infer_server_address({}, invocation_params)
        # Should not raise; either returns None or a best-effort parse
        assert result is None or isinstance(result, str)

    def test_handles_empty_string_url(self):
        invocation_params = {"base_url": ""}
        result = infer_server_address({}, invocation_params)
        assert result is None or isinstance(result, str)

    def test_invocation_params_base_url_takes_priority(self):
        serialized = {
            "kwargs": {"openai_api_base": "https://fallback.example.com/v1"}
        }
        invocation_params = {"base_url": "https://primary.example.com/v1"}
        assert (
            infer_server_address(serialized, invocation_params)
            == "primary.example.com"
        )


# ---------------------------------------------------------------------------
# infer_server_port
# ---------------------------------------------------------------------------


class TestInferServerPort:
    """Extract port from URL sources."""

    def test_explicit_port(self):
        invocation_params = {"base_url": "http://localhost:11434/v1"}
        assert infer_server_port({}, invocation_params) == 11434

    def test_no_explicit_port_returns_none(self):
        invocation_params = {"base_url": "https://api.openai.com/v1"}
        assert infer_server_port({}, invocation_params) is None

    def test_standard_http_port_returned_when_explicit(self):
        # urlparse returns port when explicitly specified, even if standard
        invocation_params = {"base_url": "http://api.example.com:80/v1"}
        assert infer_server_port({}, invocation_params) == 80

    def test_standard_https_port_returned_when_explicit(self):
        invocation_params = {"base_url": "https://api.example.com:443/v1"}
        assert infer_server_port({}, invocation_params) == 443

    def test_custom_port(self):
        invocation_params = {"base_url": "https://api.example.com:8443/v1"}
        assert infer_server_port({}, invocation_params) == 8443

    def test_returns_none_when_no_url(self):
        assert infer_server_port({}, {}) is None

    def test_returns_none_for_none_inputs(self):
        assert infer_server_port({}, None) is None

    def test_port_from_serialized_openai_api_base(self):
        serialized = {
            "kwargs": {"openai_api_base": "http://localhost:8080/v1"}
        }
        assert infer_server_port(serialized, {}) == 8080

    def test_port_from_serialized_azure_endpoint(self):
        serialized = {
            "kwargs": {
                "azure_endpoint": "https://my-resource.openai.azure.com:9090/"
            }
        }
        assert infer_server_port(serialized, {}) == 9090
