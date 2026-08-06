# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from vertexai.generative_models import (
    Content,
    FunctionDeclaration,
    GenerativeModel,
    Part,
    Tool,
)


def weather_tool() -> Tool:
    # Adapted from https://cloud.google.com/vertex-ai/generative-ai/docs/multimodal/function-calling#parallel-samples
    get_current_weather_func = FunctionDeclaration(
        name="get_current_weather",
        description="Get the current weather in a given location",
        parameters={
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The location for which to get the weather. "
                    "It can be a city name, a city name and state, or a zip code. "
                    "Examples: 'San Francisco', 'San Francisco, CA', '95616', etc.",
                },
            },
        },
    )
    return Tool(
        function_declarations=[get_current_weather_func],
    )


def ask_about_weather(generate_content: callable) -> None:
    model = GenerativeModel("gemini-2.5-pro", tools=[weather_tool()])
    # Model will respond asking for function calls
    generate_content(
        model,
        [
            # User asked about weather
            Content(
                role="user",
                parts=[
                    Part.from_text(
                        "Get weather details in New Delhi and San Francisco?"
                    ),
                ],
            ),
        ],
    )


def ask_about_weather_function_response(
    generate_content: callable,
) -> None:
    model = GenerativeModel("gemini-2.5-pro", tools=[weather_tool()])
    generate_content(
        model,
        [
            # User asked about weather
            Content(
                role="user",
                parts=[
                    Part.from_text(
                        "Get weather details in New Delhi and San Francisco?"
                    ),
                ],
            ),
            # Model requests two function calls
            Content(
                role="model",
                parts=[
                    Part.from_dict(
                        {
                            "function_call": {
                                "name": "get_current_weather",
                                "args": {"location": "New Delhi"},
                            }
                        },
                    ),
                    Part.from_dict(
                        {
                            "function_call": {
                                "name": "get_current_weather",
                                "args": {"location": "San Francisco"},
                            }
                        },
                    ),
                ],
            ),
            # User responds with function responses
            Content(
                role="user",
                parts=[
                    Part.from_function_response(
                        name="get_current_weather",
                        response={
                            "content": '{"temperature": 35, "unit": "C"}'
                        },
                    ),
                    Part.from_function_response(
                        name="get_current_weather",
                        response={
                            "content": '{"temperature": 25, "unit": "C"}'
                        },
                    ),
                ],
            ),
        ],
    )
