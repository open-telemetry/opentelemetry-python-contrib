import os
from typing import Tuple

import pytest
from langchain import hub
from langchain_aws import ChatBedrock
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_community.tools import DuckDuckGoSearchResults

import boto3
from langchain_aws import BedrockLLM

from langchain.chains import LLMChain, SequentialChain

@pytest.mark.vcr
def test_sequential_chain(instrument_legacy, span_exporter, log_exporter):
    bedrock_client = boto3.client(
        service_name='bedrock-runtime',
        region_name='us-west-2'  # Replace with your region
    )
    
    llm = BedrockLLM(
        client=bedrock_client,
        model_id="anthropic.claude-v2",
        model_kwargs={
            "max_tokens_to_sample": 500,
            "temperature": 0.7,
        },
    )
    synopsis_template = """You are a playwright. Given the title of play and the era it is set in, it is your job to write a synopsis for that title.

    Title: {title}
    Era: {era}
    Playwright: This is a synopsis for the above play:"""  # noqa: E501
    synopsis_prompt_template = PromptTemplate(
        input_variables=["title", "era"], template=synopsis_template
    )
    synopsis_chain = LLMChain(
        llm=llm, prompt=synopsis_prompt_template, output_key="synopsis", name="synopsis"
    )

    template = """You are a play critic from the New York Times. Given the synopsis of play, it is your job to write a review for that play.

    Play Synopsis:
    {synopsis}
    Review from a New York Times play critic of the above play:"""  # noqa: E501
    prompt_template = PromptTemplate(input_variables=["synopsis"], template=template)
    review_chain = LLMChain(llm=llm, prompt=prompt_template, output_key="review")

    overall_chain = SequentialChain(
        chains=[synopsis_chain, review_chain],
        input_variables=["era", "title"],
        # Here we return multiple variables
        output_variables=["synopsis", "review"],
        verbose=True,
    )
    overall_chain.invoke(
        {"title": "Tragedy at sunset on the beach", "era": "Victorian England"}
    )

    spans = span_exporter.get_finished_spans()

     langchain_spans = [
        span for span in spans 
        if span.name.startswith("chain ")
    ]
    
    assert [
        "chain synopsis",
        "chain LLMChain",
        "chain SequentialChain",
    ] == [span.name for span in langchain_spans]

    synopsis_span = next(span for span in spans if span.name == "chain synopsis")
    review_span = next(span for span in spans if span.name == "chain LLMChain")
    overall_span = next(span for span in spans if span.name == "chain SequentialChain")
    
    assert synopsis_span.kind == "SpanKind.INTERNAL"
    assert "gen_ai.prompt" in synopsis_span.attributes
    assert "gen_ai.completion" in synopsis_span.attributes
    
    synopsis_prompt = json.loads(synopsis_span.attributes["gen_ai.prompt"].replace("'", "\""))
    synopsis_completion = json.loads(synopsis_span.attributes["gen_ai.completion"].replace("'", "\""))
    
    assert synopsis_prompt == {
        "title": "Tragedy at sunset on the beach", 
        "era": "Victorian England"
    }
    assert "synopsis" in synopsis_completion
    
    assert review_span.kind == "SpanKind.INTERNAL"
    assert "gen_ai.prompt" in review_span.attributes
    assert "gen_ai.completion" in review_span.attributes
    
    review_prompt = json.loads(review_span.attributes["gen_ai.prompt"].replace("'", "\""))
    review_completion = json.loads(review_span.attributes["gen_ai.completion"].replace("'", "\""))
    
    assert "title" in review_prompt
    assert "era" in review_prompt
    assert "synopsis" in review_prompt
    assert "review" in review_completion
    
    assert overall_span.kind == "SpanKind.INTERNAL"
    assert "gen_ai.prompt" in overall_span.attributes
    assert "gen_ai.completion" in overall_span.attributes
    
    overall_prompt = json.loads(overall_span.attributes["gen_ai.prompt"].replace("'", "\""))
    overall_completion = json.loads(overall_span.attributes["gen_ai.completion"].replace("'", "\""))
    
    assert overall_prompt == {
        "title": "Tragedy at sunset on the beach", 
        "era": "Victorian England"
    }
    assert "synopsis" in overall_completion
    assert "review" in overall_completion