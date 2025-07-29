import os
from typing import Tuple

import pytest
from langchain import hub
from langchain_aws import ChatBedrock
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_community.tools import DuckDuckGoSearchResults

@pytest.mark.vcr
def test_agents(instrument_legacy, span_exporter, log_exporter):
    search = DuckDuckGoSearchResults()
    tools = [search]
    model = ChatBedrock(
        model_id="anthropic.claude-3-5-sonnet-20240620-v1:0",
        region_name="us-west-2",  
        temperature=0.9,
        max_tokens=2048,
        model_kwargs={
            "top_p": 0.9,
        },
    )
    
    prompt = hub.pull(
        "hwchase17/openai-functions-agent",
        api_key=os.environ["LANGSMITH_API_KEY"],
    )
    
    agent = create_tool_calling_agent(model, tools, prompt)
    agent_executor = AgentExecutor(agent=agent, tools=tools)

    agent_executor.invoke({"input": "When was Amazon founded?"})
    
    spans = span_exporter.get_finished_spans()
        
    assert set([span.name for span in spans]) == {
        "chat anthropic.claude-3-5-sonnet-20240620-v1:0",
        "chain LLMChain", 
        "chain AgentExecutor",
        "execute_tool search",
        "chain RunnableSequence",
        "chain ToolsAgentOutputParser",
        "chain ChatPromptTemplate",
        "chain RunnableAssign<agent_scratchpad>",
        "chain RunnableParallel<agent_scratchpad>",
        "chain RunnableLambda",
        "execute_tool duckduckgo_results_json",
    }


@pytest.mark.vcr
def test_agents_with_events_with_content(
    instrument_with_content, span_exporter, log_exporter
):
    search = DuckDuckGoSearchResults()
    tools = [search]
    model = ChatBedrock(
        model_id="anthropic.claude-3-5-sonnet-20240620-v1:0",
        region_name="us-west-2",  
        temperature=0.9,
        max_tokens=2048,
        model_kwargs={
            "top_p": 0.9,
        },
    )
    
    
    prompt = hub.pull(
        "hwchase17/openai-functions-agent",
        api_key=os.environ["LANGSMITH_API_KEY"],
    )

    agent = create_tool_calling_agent(model, tools, prompt)
    agent_executor = AgentExecutor(agent=agent, tools=tools)


    prompt = "What is AWS?"
    response = agent_executor.invoke({"input": prompt})

    spans = span_exporter.get_finished_spans()

    assert set([span.name for span in spans]) == {
        "chat anthropic.claude-3-5-sonnet-20240620-v1:0",
        "chain LLMChain", 
        "chain AgentExecutor",
        "execute_tool search",
        "chain RunnableSequence",
        "chain ToolsAgentOutputParser",
        "chain ChatPromptTemplate",
        "chain RunnableAssign<agent_scratchpad>",
        "chain RunnableParallel<agent_scratchpad>",
        "chain RunnableLambda",
        "execute_tool duckduckgo_results_json",
    }
    

@pytest.mark.vcr
def test_agents_with_events_with_no_content(
    instrument_with_no_content, span_exporter, log_exporter
):
    search = DuckDuckGoSearchResults()
    tools = [search]
    model = ChatBedrock(
        model_id="anthropic.claude-3-5-sonnet-20240620-v1:0",
        region_name="us-west-2",  
        temperature=0.9,
        max_tokens=2048,
        model_kwargs={
            "top_p": 0.9,
        },
    )

    prompt = hub.pull(
        "hwchase17/openai-functions-agent",
        api_key=os.environ["LANGSMITH_API_KEY"],
    )

    agent = create_tool_calling_agent(model, tools, prompt)
    agent_executor = AgentExecutor(agent=agent, tools=tools)

    agent_executor.invoke({"input": "What is AWS?"})

    spans = span_exporter.get_finished_spans()

   assert set([span.name for span in spans]) == {
        "chat anthropic.claude-3-5-sonnet-20240620-v1:0",
        "chain LLMChain", 
        "chain AgentExecutor",
        "execute_tool search",
        "chain RunnableSequence",
        "chain ToolsAgentOutputParser",
        "chain ChatPromptTemplate",
        "chain RunnableAssign<agent_scratchpad>",
        "chain RunnableParallel<agent_scratchpad>",
        "chain RunnableLambda",
        "execute_tool duckduckgo_results_json",
    }
