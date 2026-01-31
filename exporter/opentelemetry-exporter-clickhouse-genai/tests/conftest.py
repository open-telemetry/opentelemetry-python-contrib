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

"""Test fixtures for ClickHouse GenAI exporter tests."""

import pytest

from opentelemetry.exporter.clickhouse_genai import ClickHouseGenAIConfig


@pytest.fixture
def config():
    """Create a test configuration."""
    return ClickHouseGenAIConfig(
        endpoint="localhost:9000",
        database="test_otel_genai",
        username="default",
        password="",
        create_schema=False,  # Don't auto-create in tests
        ttl_days=1,
    )


@pytest.fixture
def genai_span_attributes():
    """Sample GenAI span attributes."""
    return {
        "gen_ai.operation.name": "chat",
        "gen_ai.system": "openai",
        "gen_ai.request.model": "gpt-4o",
        "gen_ai.response.model": "gpt-4o-2024-05-13",
        "gen_ai.response.id": "chatcmpl-123456",
        "gen_ai.usage.input_tokens": 100,
        "gen_ai.usage.output_tokens": 50,
        "llm.usage.total_tokens": 150,
        "gen_ai.request.temperature": 0.7,
        "gen_ai.request.max_tokens": 1000,
        "gen_ai.request.streaming": True,
        "gen_ai.response.finish_reasons": ["stop"],
        "gen_ai.request.available_tools": ["get_weather", "search"],
        "server.address": "api.openai.com",
        "server.port": 443,
    }


@pytest.fixture
def genai_log_body_message():
    """Sample GenAI log body for a message event."""
    return {
        "role": "user",
        "content": "What is the weather like today?",
    }


@pytest.fixture
def genai_log_body_choice():
    """Sample GenAI log body for a choice event."""
    return {
        "index": 0,
        "finish_reason": "stop",
        "message": {
            "role": "assistant",
            "content": "The weather is sunny today.",
            "tool_calls": [],
        },
    }
