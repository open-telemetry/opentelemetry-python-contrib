
> [!WARNING]
> GenAI instrumentations are moving to the
> [opentelemetry-python-genai](https://github.com/open-telemetry/opentelemetry-python-genai)
> repository, which is now their home for new development and releases. The
> instrumentations that still live in this repository only receive security
> patches and will be removed from here in the future.

| Instrumentation | Supported Packages | Metrics support | Semconv status |
| --------------- | ------------------ | --------------- | -------------- |
| [opentelemetry-instrumentation-genai-anthropic](https://github.com/open-telemetry/opentelemetry-python-genai/tree/main/instrumentation/opentelemetry-instrumentation-genai-anthropic) | anthropic >= 0.16.0 | Yes | development
| [opentelemetry-instrumentation-genai-claude-agent-sdk](https://github.com/open-telemetry/opentelemetry-python-genai/tree/main/instrumentation/opentelemetry-instrumentation-genai-claude-agent-sdk) | claude-agent-sdk >= 0.1.14 | No | development
| [opentelemetry-instrumentation-google-genai](./opentelemetry-instrumentation-google-genai) | google-genai >= 1.32.0 | No | development
| [opentelemetry-instrumentation-genai-langchain](https://github.com/open-telemetry/opentelemetry-python-genai/tree/main/instrumentation/opentelemetry-instrumentation-genai-langchain) | langchain >= 0.3.21 | Yes | development
| [opentelemetry-instrumentation-openai-agents-v2](./opentelemetry-instrumentation-openai-agents-v2) | openai-agents >= 0.3.3 | No | development
| [opentelemetry-instrumentation-openai-v2](./opentelemetry-instrumentation-openai-v2) | openai >= 1.26.0 | Yes | development
| [opentelemetry-instrumentation-vertexai](./opentelemetry-instrumentation-vertexai) | google-cloud-aiplatform >= 1.64 | No | development
| [opentelemetry-instrumentation-genai-weaviate-client](https://github.com/open-telemetry/opentelemetry-python-genai/tree/main/instrumentation/opentelemetry-instrumentation-genai-weaviate-client) | weaviate-client >= 3.0.0,<5.0.0 | No | development