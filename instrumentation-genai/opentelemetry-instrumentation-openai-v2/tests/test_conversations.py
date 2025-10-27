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

import os
import openai
import pytest
from packaging import version as package_version

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)

# Skip all tests in this file if OpenAI version doesn't support conversations API
pytestmark = pytest.mark.skipif(
    package_version.parse(openai.__version__) < package_version.parse("1.101.0"),
    reason="Conversations API requires OpenAI >= 1.101.0",
)


@pytest.mark.vcr()
def test_conversations_create(
    span_exporter, log_exporter, openai_client, instrument_with_content
):
    conversation = openai_client.conversations.create()

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    
    span = spans[0]
    assert span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME] == "create_conversation"
    assert span.attributes[GenAIAttributes.GEN_AI_SYSTEM] == "openai"
    assert "gen_ai.conversation.id" in span.attributes
    assert span.attributes["gen_ai.conversation.id"] == conversation.id


@pytest.mark.vcr()
def test_conversation_items_list_with_content(
    span_exporter, log_exporter, openai_client, instrument_with_content
):
    # First create a conversation to get a conversation ID
    conversation = openai_client.conversations.create()
    
    # Add some messages to the conversation to create items
    openai_client.responses.create(
        conversation=conversation.id,
        model="gpt-4o-mini",
        input="Say hello"
    )
    
    # Clear spans from conversation creation and response
    span_exporter.clear()
    
    # List conversation items
    items = openai_client.conversations.items.list(conversation_id=conversation.id)
    
    # Iterate over items to trigger the instrumentation
    item_list = list(items)

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    
    span = spans[0]
    assert span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME] == "list_conversation_items"
    assert span.attributes[GenAIAttributes.GEN_AI_SYSTEM] == "openai"
    assert "gen_ai.conversation.id" in span.attributes
    assert span.attributes["gen_ai.conversation.id"] == conversation.id

    # Check events for conversation items when capture_content is True
    events = span.events
    # Should have events for the conversation items (user input + assistant response)
    assert len(events) >= 1


@pytest.mark.vcr()
def test_conversation_items_list_no_content(
    span_exporter, log_exporter, openai_client, instrument_no_content
):
    # First create a conversation to get a conversation ID
    conversation = openai_client.conversations.create()
    
    # Add some messages to the conversation to create items
    openai_client.responses.create(
        conversation=conversation.id,
        model="gpt-4o-mini",
        input="Say hello"
    )
    
    # Clear spans from conversation creation and response
    span_exporter.clear()
    
    # List conversation items
    items = openai_client.conversations.items.list(conversation_id=conversation.id)
    
    # Iterate over items to trigger the instrumentation
    item_list = list(items)

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    
    span = spans[0]
    assert span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME] == "list_conversation_items"
    assert span.attributes[GenAIAttributes.GEN_AI_SYSTEM] == "openai"
    assert "gen_ai.conversation.id" in span.attributes
    assert span.attributes["gen_ai.conversation.id"] == conversation.id

    # Check span events - no content should be captured when capture_content is False
    events = span.events
    for event in events:
        if hasattr(event, 'attributes') and event.attributes:
            assert "gen_ai.event.content" not in event.attributes or not event.attributes.get("gen_ai.event.content")
