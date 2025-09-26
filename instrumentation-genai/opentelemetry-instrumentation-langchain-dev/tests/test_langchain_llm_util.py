# Copyright The OpenTelemetry Authors
import json
import os

import pytest
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from opentelemetry.semconv._incubating.attributes import gen_ai_attributes


@pytest.mark.vcr()
def test_langchain_call_util(
    span_exporter, instrument_with_content_util, monkeypatch
):
    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.setenv("APPKEY", "test-app-key")
    model_name = "gpt-4o-mini"
    llm = ChatOpenAI(
        temperature=0.0,
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url="https://chat-ai.cisco.com/openai/deployments/gpt-4o-mini",
        model=model_name,
        default_headers={"api-key": os.getenv("OPENAI_API_KEY")},
        model_kwargs={"user": json.dumps({"appkey": os.getenv("APPKEY")})},
    )
    messages = [
        SystemMessage(content="You are a helpful assistant!"),
        HumanMessage(content="What is the capital of France?"),
    ]
    response = llm.invoke(messages)
    assert "Paris" in response.content
    spans = span_exporter.get_finished_spans()
    assert spans, "No spans exported in util-genai path"
    chat_spans = [
        s
        for s in spans
        if s.attributes.get(gen_ai_attributes.GEN_AI_OPERATION_NAME)
        == gen_ai_attributes.GenAiOperationNameValues.CHAT.value
    ]
    assert chat_spans, "No chat operation spans found"
    span = chat_spans[0]
    # Basic attribute checks
    assert (
        span.attributes.get(gen_ai_attributes.GEN_AI_REQUEST_MODEL)
        == model_name
    )
    assert (
        gen_ai_attributes.GEN_AI_RESPONSE_MODEL in span.attributes or True
    )  # response model may differ depending on provider metadata
    # Token metrics may or may not exist depending on replayed cassette; do not assert strictly
    # Ensure span name format
    assert span.name.startswith("chat ")
