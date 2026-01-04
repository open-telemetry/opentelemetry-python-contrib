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

"""Method wrappers for CrewAI instrumentation."""

from __future__ import annotations

import json
import time
from typing import Any, Callable

from opentelemetry.metrics import Histogram
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.trace import SpanKind, Tracer
from opentelemetry.trace.status import Status, StatusCode

from opentelemetry.instrumentation.crewai.utils import (
    dont_throw,
    safe_json_serialize,
    set_span_attribute,
    should_capture_content,
)

# Custom semantic attributes for CrewAI (following gen_ai.* namespace)
# Operation name attribute (OTel standard)
GENAI_OPERATION_NAME = "gen_ai.operation.name"

# Crew-specific attributes
CREWAI_CREW_NAME = "gen_ai.crewai.crew.name"
CREWAI_CREW_TASKS = "gen_ai.crewai.crew.tasks"
CREWAI_CREW_AGENTS = "gen_ai.crewai.crew.agents"
CREWAI_CREW_RESULT = "gen_ai.crewai.crew.result"
CREWAI_CREW_TASKS_OUTPUT = "gen_ai.crewai.crew.tasks_output"
CREWAI_CREW_TOKEN_USAGE = "gen_ai.crewai.crew.token_usage"
CREWAI_CREW_USAGE_METRICS = "gen_ai.crewai.crew.usage_metrics"

# Agent-specific attributes
CREWAI_AGENT_ROLE = "gen_ai.crewai.agent.role"
CREWAI_AGENT_GOAL = "gen_ai.crewai.agent.goal"
CREWAI_AGENT_BACKSTORY = "gen_ai.crewai.agent.backstory"
CREWAI_AGENT_TOOLS = "gen_ai.crewai.agent.tools"
CREWAI_AGENT_MAX_ITER = "gen_ai.crewai.agent.max_iter"
CREWAI_AGENT_ALLOW_DELEGATION = "gen_ai.crewai.agent.allow_delegation"
CREWAI_AGENT_VERBOSE = "gen_ai.crewai.agent.verbose"

# Task-specific attributes
CREWAI_TASK_DESCRIPTION = "gen_ai.crewai.task.description"
CREWAI_TASK_EXPECTED_OUTPUT = "gen_ai.crewai.task.expected_output"
CREWAI_TASK_AGENT = "gen_ai.crewai.task.agent"
CREWAI_TASK_TOOLS = "gen_ai.crewai.task.tools"
CREWAI_TASK_ASYNC_EXECUTION = "gen_ai.crewai.task.async_execution"
CREWAI_TASK_HUMAN_INPUT = "gen_ai.crewai.task.human_input"
CREWAI_TASK_OUTPUT = "gen_ai.crewai.task.output"

# LLM-specific attributes
CREWAI_LLM_MODEL = "gen_ai.crewai.llm.model"
CREWAI_LLM_TEMPERATURE = "gen_ai.crewai.llm.temperature"
CREWAI_LLM_TOP_P = "gen_ai.crewai.llm.top_p"
CREWAI_LLM_MAX_TOKENS = "gen_ai.crewai.llm.max_tokens"

# Entity input/output (for content capture)
CREWAI_ENTITY_INPUT = "gen_ai.crewai.entity.input"
CREWAI_ENTITY_OUTPUT = "gen_ai.crewai.entity.output"


def _serialize_tools(tools: Any) -> str:
    """Serialize tools list to JSON string.

    Args:
        tools: List of tool objects.

    Returns:
        JSON string representation of tools.
    """
    if not tools:
        return "[]"
    try:
        return json.dumps(
            [
                {k: v for k, v in vars(tool).items()
                 if v is not None and k in ["name", "description"]}
                for tool in tools
            ]
        )
    except Exception:
        return str(tools)


def _extract_crew_data(instance: Any) -> dict[str, Any]:
    """Extract crew data for span attributes.

    Args:
        instance: CrewAI Crew instance.

    Returns:
        Dictionary of crew attributes.
    """
    data: dict[str, Any] = {}

    # Extract tasks
    if hasattr(instance, "tasks") and instance.tasks:
        tasks_data = []
        for task in instance.tasks:
            task_info = {
                "description": getattr(task, "description", None),
                "expected_output": getattr(task, "expected_output", None),
                "async_execution": getattr(task, "async_execution", False),
            }
            if hasattr(task, "agent") and task.agent:
                task_info["agent"] = getattr(task.agent, "role", None)
            tasks_data.append(task_info)
        data["tasks"] = safe_json_serialize(tasks_data)

    # Extract agents
    if hasattr(instance, "agents") and instance.agents:
        agents_data = []
        for agent in instance.agents:
            agent_info = {
                "role": getattr(agent, "role", None),
                "goal": getattr(agent, "goal", None),
                "backstory": getattr(agent, "backstory", None),
                "allow_delegation": getattr(agent, "allow_delegation", False),
                "max_iter": getattr(agent, "max_iter", None),
            }
            # Get LLM model name
            if hasattr(agent, "llm"):
                model = getattr(agent.llm, "model", None) or getattr(
                    agent.llm, "model_name", None
                )
                if model:
                    agent_info["llm"] = str(model)
            agents_data.append(agent_info)
        data["agents"] = safe_json_serialize(agents_data)

    return data


def _extract_agent_data(instance: Any) -> dict[str, Any]:
    """Extract agent data for span attributes.

    Args:
        instance: CrewAI Agent instance.

    Returns:
        Dictionary of agent attributes.
    """
    data: dict[str, Any] = {}

    if hasattr(instance, "role"):
        data["role"] = instance.role
    if hasattr(instance, "goal"):
        data["goal"] = instance.goal
    if hasattr(instance, "backstory"):
        data["backstory"] = instance.backstory
    if hasattr(instance, "allow_delegation"):
        data["allow_delegation"] = instance.allow_delegation
    if hasattr(instance, "max_iter"):
        data["max_iter"] = instance.max_iter
    if hasattr(instance, "verbose"):
        data["verbose"] = instance.verbose
    if hasattr(instance, "tools") and instance.tools:
        data["tools"] = _serialize_tools(instance.tools)

    return data


def _extract_task_data(instance: Any) -> dict[str, Any]:
    """Extract task data for span attributes.

    Args:
        instance: CrewAI Task instance.

    Returns:
        Dictionary of task attributes.
    """
    data: dict[str, Any] = {}

    if hasattr(instance, "description"):
        data["description"] = instance.description
    if hasattr(instance, "expected_output"):
        data["expected_output"] = instance.expected_output
    if hasattr(instance, "async_execution"):
        data["async_execution"] = instance.async_execution
    if hasattr(instance, "human_input"):
        data["human_input"] = instance.human_input
    if hasattr(instance, "agent") and instance.agent:
        data["agent"] = getattr(instance.agent, "role", None)
    if hasattr(instance, "tools") and instance.tools:
        data["tools"] = _serialize_tools(instance.tools)

    return data


def _extract_llm_data(instance: Any) -> dict[str, Any]:
    """Extract LLM data for span attributes.

    Args:
        instance: CrewAI LLM instance.

    Returns:
        Dictionary of LLM attributes.
    """
    data: dict[str, Any] = {}

    fields_mapping = {
        "model": "model",
        "temperature": "temperature",
        "top_p": "top_p",
        "max_tokens": "max_tokens",
        "max_completion_tokens": "max_completion_tokens",
        "presence_penalty": "presence_penalty",
        "frequency_penalty": "frequency_penalty",
        "seed": "seed",
    }

    for field, key in fields_mapping.items():
        value = getattr(instance, field, None)
        if value is not None:
            data[key] = value

    return data


def create_kickoff_wrapper(
    tracer: Tracer,
    duration_histogram: Histogram | None = None,
    token_histogram: Histogram | None = None,
) -> Callable[..., Any]:
    """Create wrapper for Crew.kickoff.

    Args:
        tracer: The OpenTelemetry tracer.
        duration_histogram: Optional histogram for recording duration.
        token_histogram: Optional histogram for recording token usage.

    Returns:
        The wrapper function.
    """

    def wrapper(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        with tracer.start_as_current_span(
            name="crewai.workflow",
            kind=SpanKind.INTERNAL,
        ) as span:
            # Set standard GenAI attributes
            span.set_attribute(GenAIAttributes.GEN_AI_SYSTEM, "crewai")
            span.set_attribute(GENAI_OPERATION_NAME, "workflow")

            # Extract and set crew data
            crew_data = _extract_crew_data(instance)
            if "tasks" in crew_data:
                set_span_attribute(span, CREWAI_CREW_TASKS, crew_data["tasks"])
            if "agents" in crew_data:
                set_span_attribute(
                    span, CREWAI_CREW_AGENTS, crew_data["agents"]
                )

            start_time = time.perf_counter()

            try:
                result = wrapped(*args, **kwargs)

                # Set result attributes
                if result:
                    set_span_attribute(
                        span, CREWAI_CREW_RESULT, str(result)[:1000]
                    )  # Limit result size

                    # Extract additional result attributes
                    for attr in ["tasks_output", "token_usage", "usage_metrics"]:
                        if hasattr(result, attr):
                            attr_value = getattr(result, attr)
                            if attr_value is not None:
                                set_span_attribute(
                                    span,
                                    f"gen_ai.crewai.crew.{attr}",
                                    safe_json_serialize(attr_value),
                                )

                span.set_status(Status(StatusCode.OK))
                return result

            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

            finally:
                if duration_histogram is not None:
                    duration = time.perf_counter() - start_time
                    duration_histogram.record(
                        duration,
                        attributes={
                            GenAIAttributes.GEN_AI_SYSTEM: "crewai",
                            GENAI_OPERATION_NAME: "workflow",
                        },
                    )

    return wrapper


def create_agent_execute_task_wrapper(
    tracer: Tracer,
    duration_histogram: Histogram | None = None,
    token_histogram: Histogram | None = None,
) -> Callable[..., Any]:
    """Create wrapper for Agent.execute_task.

    Args:
        tracer: The OpenTelemetry tracer.
        duration_histogram: Optional histogram for recording duration.
        token_histogram: Optional histogram for recording token usage.

    Returns:
        The wrapper function.
    """

    def wrapper(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        agent_role = getattr(instance, "role", "agent")

        with tracer.start_as_current_span(
            name=f"{agent_role}.agent",
            kind=SpanKind.CLIENT,
        ) as span:
            # Set standard GenAI attributes
            span.set_attribute(GenAIAttributes.GEN_AI_SYSTEM, "crewai")
            span.set_attribute(GENAI_OPERATION_NAME, "agent")

            # Extract and set agent data
            agent_data = _extract_agent_data(instance)
            if "role" in agent_data:
                set_span_attribute(span, CREWAI_AGENT_ROLE, agent_data["role"])
            if "goal" in agent_data:
                set_span_attribute(span, CREWAI_AGENT_GOAL, agent_data["goal"])
            if "backstory" in agent_data:
                set_span_attribute(
                    span, CREWAI_AGENT_BACKSTORY, agent_data["backstory"]
                )
            if "tools" in agent_data:
                set_span_attribute(
                    span, CREWAI_AGENT_TOOLS, agent_data["tools"]
                )
            if "max_iter" in agent_data:
                set_span_attribute(
                    span, CREWAI_AGENT_MAX_ITER, agent_data["max_iter"]
                )
            if "allow_delegation" in agent_data:
                set_span_attribute(
                    span,
                    CREWAI_AGENT_ALLOW_DELEGATION,
                    agent_data["allow_delegation"],
                )

            # Get model name if available
            model_name = None
            if hasattr(instance, "llm"):
                model_name = getattr(instance.llm, "model", None) or getattr(
                    instance.llm, "model_name", None
                )
                if model_name:
                    set_span_attribute(
                        span, GenAIAttributes.GEN_AI_REQUEST_MODEL, str(model_name)
                    )
                    set_span_attribute(
                        span, GenAIAttributes.GEN_AI_RESPONSE_MODEL, str(model_name)
                    )

            start_time = time.perf_counter()

            try:
                result = wrapped(*args, **kwargs)

                # Record token usage if available
                if token_histogram is not None and hasattr(
                    instance, "_token_process"
                ):
                    try:
                        summary = instance._token_process.get_summary()
                        if summary and model_name:
                            if hasattr(summary, "prompt_tokens"):
                                token_histogram.record(
                                    summary.prompt_tokens,
                                    attributes={
                                        GenAIAttributes.GEN_AI_SYSTEM: "crewai",
                                        GenAIAttributes.GEN_AI_TOKEN_TYPE: "input",
                                        GenAIAttributes.GEN_AI_RESPONSE_MODEL: str(
                                            model_name
                                        ),
                                    },
                                )
                            if hasattr(summary, "completion_tokens"):
                                token_histogram.record(
                                    summary.completion_tokens,
                                    attributes={
                                        GenAIAttributes.GEN_AI_SYSTEM: "crewai",
                                        GenAIAttributes.GEN_AI_TOKEN_TYPE: "output",
                                        GenAIAttributes.GEN_AI_RESPONSE_MODEL: str(
                                            model_name
                                        ),
                                    },
                                )
                    except Exception:
                        pass  # Don't fail if token tracking fails

                span.set_status(Status(StatusCode.OK))
                return result

            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

            finally:
                if duration_histogram is not None and model_name:
                    duration = time.perf_counter() - start_time
                    duration_histogram.record(
                        duration,
                        attributes={
                            GenAIAttributes.GEN_AI_SYSTEM: "crewai",
                            GenAIAttributes.GEN_AI_RESPONSE_MODEL: str(model_name),
                            GENAI_OPERATION_NAME: "agent",
                        },
                    )

    return wrapper


def create_task_execute_wrapper(
    tracer: Tracer,
    duration_histogram: Histogram | None = None,
    token_histogram: Histogram | None = None,
) -> Callable[..., Any]:
    """Create wrapper for Task.execute_sync.

    Args:
        tracer: The OpenTelemetry tracer.
        duration_histogram: Optional histogram for recording duration.
        token_histogram: Optional histogram for recording token usage.

    Returns:
        The wrapper function.
    """

    def wrapper(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        task_description = getattr(instance, "description", "task")
        # Truncate long task descriptions for span name
        task_name = (
            task_description[:50] + "..."
            if len(task_description) > 50
            else task_description
        )

        with tracer.start_as_current_span(
            name=f"{task_name}.task",
            kind=SpanKind.CLIENT,
        ) as span:
            # Set standard GenAI attributes
            span.set_attribute(GenAIAttributes.GEN_AI_SYSTEM, "crewai")
            span.set_attribute(GENAI_OPERATION_NAME, "task")

            # Extract and set task data
            task_data = _extract_task_data(instance)
            if "description" in task_data:
                set_span_attribute(
                    span, CREWAI_TASK_DESCRIPTION, task_data["description"]
                )
            if "expected_output" in task_data:
                set_span_attribute(
                    span, CREWAI_TASK_EXPECTED_OUTPUT, task_data["expected_output"]
                )
            if "agent" in task_data:
                set_span_attribute(span, CREWAI_TASK_AGENT, task_data["agent"])
            if "tools" in task_data:
                set_span_attribute(span, CREWAI_TASK_TOOLS, task_data["tools"])
            if "async_execution" in task_data:
                set_span_attribute(
                    span, CREWAI_TASK_ASYNC_EXECUTION, task_data["async_execution"]
                )
            if "human_input" in task_data:
                set_span_attribute(
                    span, CREWAI_TASK_HUMAN_INPUT, task_data["human_input"]
                )

            try:
                result = wrapped(*args, **kwargs)

                # Capture output if content capture is enabled
                if should_capture_content() and result:
                    set_span_attribute(
                        span, CREWAI_TASK_OUTPUT, str(result)[:2000]
                    )

                span.set_status(Status(StatusCode.OK))
                return result

            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

    return wrapper


def create_llm_call_wrapper(
    tracer: Tracer,
    duration_histogram: Histogram | None = None,
    token_histogram: Histogram | None = None,
) -> Callable[..., Any]:
    """Create wrapper for LLM.call.

    Args:
        tracer: The OpenTelemetry tracer.
        duration_histogram: Optional histogram for recording duration.
        token_histogram: Optional histogram for recording token usage.

    Returns:
        The wrapper function.
    """

    def wrapper(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        model_name = getattr(instance, "model", "llm")

        with tracer.start_as_current_span(
            name=f"{model_name}.llm",
            kind=SpanKind.CLIENT,
        ) as span:
            # Set standard GenAI attributes
            span.set_attribute(GenAIAttributes.GEN_AI_SYSTEM, "crewai")
            span.set_attribute(GENAI_OPERATION_NAME, "chat")

            # Extract and set LLM data
            llm_data = _extract_llm_data(instance)
            if "model" in llm_data:
                set_span_attribute(
                    span, GenAIAttributes.GEN_AI_REQUEST_MODEL, str(llm_data["model"])
                )
                set_span_attribute(
                    span, GenAIAttributes.GEN_AI_RESPONSE_MODEL, str(llm_data["model"])
                )
            if "temperature" in llm_data:
                set_span_attribute(
                    span,
                    GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE,
                    llm_data["temperature"],
                )
            if "top_p" in llm_data:
                set_span_attribute(
                    span, GenAIAttributes.GEN_AI_REQUEST_TOP_P, llm_data["top_p"]
                )
            if "max_tokens" in llm_data:
                set_span_attribute(
                    span,
                    GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS,
                    llm_data["max_tokens"],
                )

            start_time = time.perf_counter()

            try:
                result = wrapped(*args, **kwargs)
                span.set_status(Status(StatusCode.OK))
                return result

            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

            finally:
                if duration_histogram is not None:
                    duration = time.perf_counter() - start_time
                    duration_histogram.record(
                        duration,
                        attributes={
                            GenAIAttributes.GEN_AI_SYSTEM: "crewai",
                            GenAIAttributes.GEN_AI_RESPONSE_MODEL: str(model_name),
                        },
                    )

    return wrapper
