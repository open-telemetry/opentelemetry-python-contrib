# pylint: skip-file
import json
import os
import uuid

from openai import OpenAI
# NOTE: OpenTelemetry Python Logs and Events APIs are in beta
from opentelemetry import _events, _logs, trace
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (
    OTLPLogExporter,
)
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor
from opentelemetry.sdk._events import EventLoggerProvider
from opentelemetry.sdk._logs import LoggerProvider, LogRecordProcessor, LogData
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from dotenv import load_dotenv
load_dotenv()

# configure tracing
trace.set_tracer_provider(TracerProvider())
trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter())
)

# configure logging and events
_logs.set_logger_provider(LoggerProvider())
_logs.get_logger_provider().add_log_record_processor(
    BatchLogRecordProcessor(OTLPLogExporter())
)
_events.set_event_logger_provider(EventLoggerProvider())


def prompt_uploader(span, event, prompt):
    attribute_name = "gen_ai.request.inputs_ref"
    ref = f"https://my-storage/bucket/{uuid.uuid4()}"
    print(f"Uploading prompt to {ref}, prompt: {prompt}")

    if span.is_recording():
        span.set_attribute(attribute_name, ref)
        span.set_attribute("gen_ai.request.inputs", "")
        
    if event:
        event.attributes[attribute_name] = ref
        event.body = f"prompt uploaded to {ref}"

def completion_uploader(span, event, completion):
    attribute_name = "gen_ai.response.outputs_ref"
    ref = f"https://my-storage/bucket/{uuid.uuid4()}"
    print(f"Uploading completion to {ref}, completion: {completion}")

    if span.is_recording():
        span.set_attribute(attribute_name, ref)
        span.set_attribute("gen_ai.response.outputs", "")
        
    if event:
        event.attributes[attribute_name] = ref
        event.body = f"completion uploaded to {ref}"
        
OpenAIInstrumentor().instrument(
    capture_sensitive_content=True,  # the same as existing OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT env var
    capture_verbose_attributes=True, 
    
    # | sensitive_content | verbose_attributes | Result                                                                                                                         |
    # |-------------------|--------------------|------------------------------------------------------------------------------------------------------------------------------- |
    # | False (default)   | False (default)    | Prompts/completions - not captured. Not-sensitive opt-in attributes - not captured                                             |
    # | False (default)   | True               | Prompts/completions - not captured. Not-sensitive opt-in attributes - captured                                                 |
    # | True              | False (default)    | Prompts/completions - captured on events if DEBUG level is enabled. Not-sensitive opt-in attributes - not captured             |
    # | True              | True               | Prompts/completions - captured on attributes and events if DEBUG level is enabled. Not-sensitive opt-in attributes - captured  |
    # can probably merge two flags in one enum

    # optional hooks, independent from above flags:
    # prompt_hook=prompt_uploader,
    # completion_hook=completion_uploader
)

weather_tool = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get current weather for a given location",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City or location name"}
            },
            "required": ["location"]
        }
    }
}

location_tool  = {
    "type": "function",
    "function": {
        "name": "get_location",
        "description": "Get location information",
        "parameters": {
        }
    }
}

response_format = {
    "type": "json_schema",
    "json_schema": {
        "name":"weather_forecast",
        "schema" : {
            "type": "object",
            "properties": {
                "temperature": {
                    "type": "string",
                },
                "precipitation": {
                    "type": "string",
                },
            },
            "required": ["temperature"],
            "additionalProperties": True,
        }
    }
}

tracer = trace.get_tracer(__name__)
@tracer.start_as_current_span("main")
def main():
    client = OpenAI()
    model=os.getenv("CHAT_MODEL", "gpt-4o-mini")

    messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {
                "role": "user",
                "content": "What is the weather like?",
            },
        ]

    chat_completion = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=[location_tool, weather_tool],
        response_format=response_format
    )

    while chat_completion.choices[0].finish_reason == "tool_calls":
        messages.append(chat_completion.choices[0].message)
        # Call the tool with the response from the model
        for call in chat_completion.choices[0].message.tool_calls:
            function_args = json.loads(call.function.arguments)
            if call.function.name == "get_weather":
                messages.append(
                    {"tool_call_id": call.id,
                    "role": "tool",
                    "name": "get_weather",
                    "content": f"Weather in {function_args['location']} is sunny and 75 degrees."})
            if call.function.name == "get_location":
                messages.append(
                    {"tool_call_id": call.id,
                    "role": "tool",
                    "name": "get_location",
                    "content": "Seattle, WA"})
        chat_completion = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=[location_tool, weather_tool],
            response_format=response_format)

    print(chat_completion.choices[0].message.content)


if __name__ == "__main__":
    main()
