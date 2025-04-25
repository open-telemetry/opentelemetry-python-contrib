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

from typing import Any, Callable, Optional, Union

import functools
import inspect


from opentelemetry import trace
from opentelemetry.semconv._incubating.attributes import (
    code_attributes,
)
from google.genai.types import (
    ToolOrDict,
    ToolListUnion,
    ToolListUnionDict,
)
from .custom_semconv import (
    CODE_MODULE,
    FUNCTION_TOOL_CALL_START_EVENT_ATTRS_POSITIONAL_ARGS_COUNT,
    FUNCTION_TOOL_CALL_START_EVENT_ATTRS_KEYWORD_ARGS_COUNT,
    FUNCTION_TOOL_CALL_START_EVENT_BODY_POSITIONAL_ARGS,
    FUNCTION_TOOL_CALL_START_EVENT_BODY_KEYWORD_ARGS,
    FUNCTION_TOOL_CALL_END_EVENT_BODY_RESULT,
    TOOL_CALL_POSITIONAL_ARG_COUNT,
    TOOL_CALL_KEYWORD_ARG_COUNT,
)
from .flags import is_content_recording_enabled
from .otel_wrapper import OTelWrapper


ToolFunction = Callable[..., Any]


def _to_otel_value(python_value):
    """Coerces parameters to something representable with Open Telemetry."""
    if python_value is None:
        return None
    if isinstance(python_value, list):
        return [_to_otel_value(x) for x in python_value]
    if isinstance(python_value, dict): 
        return dict([(key, _to_otel_value(val)) for (key, val) in python_value.items()])
    if hasattr(python_value, "model_dump"):
        return python_value.model_dump()
    if hasattr(python_value, "__dict__"):
        return _to_otel_value(python_value.__dict__)
    return repr(python_value)


def _create_function_span_name(wrapped_function):
    """Constructs the span name for a given local function tool call.""" 
    function_name = wrapped_function.__name__
    return f"tool_call {function_name}"


def _create_function_span_attributes(
    wrapped_function,
    function_args,
    function_kwargs,
    extra_span_attributes):
    """Creates the attributes for a tool call function span."""
    result = {}
    if extra_span_attributes:
        result.update(extra_span_attributes)
    result[code_attributes.CODE_FUNCTION_NAME] = wrapped_function.__name__
    result[CODE_MODULE] = wrapped_function.__module__
    result[TOOL_CALL_POSITIONAL_ARG_COUNT] = len(function_args)
    result[TOOL_CALL_KEYWORD_ARG_COUNT] = len(function_kwargs)
    return result


def _record_function_call_event(
    otel_wrapper,
    wrapped_function,
    function_args,
    function_kwargs):
  """Records the details about a function invocation as a log event."""
  attributes = {
    code_attributes.CODE_FUNCTION_NAME: wrapped_function.__name__,
    CODE_MODULE: wrapped_function.__module__,
    FUNCTION_TOOL_CALL_START_EVENT_ATTRS_POSITIONAL_ARGS_COUNT: len(function_args),
    FUNCTION_TOOL_CALL_START_EVENT_ATTRS_KEYWORD_ARGS_COUNT: len(function_kwargs)
  }
  body = {}
  if is_content_recording_enabled():
    body[FUNCTION_TOOL_CALL_START_EVENT_BODY_POSITIONAL_ARGS] = _to_otel_value(function_args)
    body[FUNCTION_TOOL_CALL_START_EVENT_BODY_KEYWORD_ARGS] = _to_otel_value(function_kwargs)
  otel_wrapper.log_function_call_start(attributes, body)


def _record_function_call_result_event(
    otel_wrapper,
    wrapped_function,
    result):
  attributes = {
    code_attributes.CODE_FUNCTION_NAME: wrapped_function.__name__,
    CODE_MODULE: wrapped_function.__module__,
  }
  body = {}
  if is_content_recording_enabled():
    body[FUNCTION_TOOL_CALL_END_EVENT_BODY_RESULT] = _to_otel_value(result)
  otel_wrapper.log_function_call_end(attributes, body)


def _wrap_sync_tool_function(
    tool_function: ToolFunction,
    otel_wrapper: OTelWrapper,
    extra_span_attributes: Optional[dict[str, str]] = None,
    **kwargs):
    @functools.wraps(tool_function)
    def wrapped_function(*args, **kwargs):
        span_name = _create_function_span_name(tool_function)
        attributes = _create_function_span_attributes(tool_function, args, kwargs, extra_span_attributes)
        with otel_wrapper.start_as_current_span(span_name, attributes=attributes):
            _record_function_call_event(otel_wrapper, tool_function, args, kwargs)
            result = tool_function(*args, **kwargs)
            _record_function_call_result_event(otel_wrapper, tool_function, result)
            return result
    return wrapped_function


def _wrap_async_tool_function(
    tool_function: ToolFunction,
    otel_wrapper: OTelWrapper,
    extra_span_attributes: Optional[dict[str, str]] = None,
    **kwargs):
    @functools.wraps(tool_function)
    async def wrapped_function(*args, **kwargs):
        span_name = _create_function_span_name(tool_function)
        attributes = _create_function_span_attributes(tool_function, args, kwargs, extra_span_attributes)
        with otel_wrapper.start_as_current_span(span_name, attributes=attributes):
            _record_function_call_event(otel_wrapper, tool_function, args, kwargs)
            result = await tool_function(*args, **kwargs)
            _record_function_call_result_event(otel_wrapper, tool_function, result)
            return result
    return wrapped_function


def _wrap_tool_function(tool_function: ToolFunction, otel_wrapper: OTelWrapper, **kwargs):
    if inspect.iscoroutinefunction(tool_function):
        return _wrap_async_tool_function(tool_function, otel_wrapper, **kwargs)
    return _wrap_sync_tool_function(tool_function, otel_wrapper, **kwargs)


def wrapped(
    tool_or_tools: Optional[Union[ToolFunction, ToolOrDict, ToolListUnion, ToolListUnionDict]],
    otel_wrapper: OTelWrapper,
    **kwargs):
    if tool_or_tools is None:
        return None
    if isinstance(tool_or_tools, list):
        return [wrapped(item, otel_wrapper, **kwargs) for item in tool_or_tools]
    if isinstance(tool_or_tools, dict):
        return dict([(key, wrapped(value, otel_wrapper, **kwargs)) for (key, value) in tool_or_tools.items()])
    if callable(tool_or_tools):
        return _wrap_tool_function(tool_or_tools, otel_wrapper, **kwargs)
    return tool_or_tools
