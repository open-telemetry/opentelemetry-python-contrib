from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


from opentelemetry.sdk._events import EventLoggerProvider
from opentelemetry.sdk._logs.export import (
    InMemoryLogExporter,
    SimpleLogRecordProcessor,
)

from opentelemetry.sdk.metrics import (
    MeterProvider,
)
from opentelemetry.sdk.metrics.export import (
    InMemoryMetricReader,
)

from opentelemetry.instrumentation.langchain import LangChainInstrumentor

@pytest.fixture(scope="function", name="span_exporter")
def fixture_span_exporter():
    exporter = InMemorySpanExporter()
    yield exporter


@pytest.fixture(scope="function", name="log_exporter")
def fixture_log_exporter():
    exporter = InMemoryLogExporter()
    yield exporter


@pytest.fixture(scope="function", name="metric_reader")
def fixture_metric_reader():
    exporter = InMemoryMetricReader()
    yield exporter


@pytest.fixture(scope="function", name="tracer_provider")
def fixture_tracer_provider(span_exporter):
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    return provider


# # not sure if needed
# @pytest.fixture(scope="function", name="event_logger_provider")
# def fixture_event_logger_provider(log_exporter):
#     provider = LoggerProvider()
#     provider.add_log_record_processor(SimpleLogRecordProcessor(log_exporter))
#     event_logger_provider = EventLoggerProvider(provider)

#     return event_logger_provider


# # not sure if needed
# @pytest.fixture(scope="function", name="meter_provider")
# def fixture_meter_provider(metric_reader):
#     meter_provider = MeterProvider(
#         metric_readers=[metric_reader],
#     )

#     return meter_provider


@pytest.fixture(autouse=True)
def environment():

    if not os.getenv("AWS_ACCESS_KEY_ID"):
        os.environ["AWS_ACCESS_KEY_ID"] = "test_aws_access_key_id"
    
    if not os.getenv("AWS_SECRET_ACCESS_KEY"):
        os.environ["AWS_SECRET_ACCESS_KEY"] = "test_aws_secret_access_key"
    
    if not os.getenv("AWS_REGION"):
        os.environ["AWS_REGION"] = "us-west-2"
    
    if not os.getenv("AWS_BEDROCK_ENDPOINT_URL"):
        os.environ["AWS_BEDROCK_ENDPOINT_URL"] = "https://bedrock.us-west-2.amazonaws.com"
    
    if not os.getenv("AWS_PROFILE"):
        os.environ["AWS_PROFILE"] = "default"




def scrub_aws_credentials(response):
    """Remove sensitive data from response headers."""
    if "headers" in response:
        for sensitive_header in [
            "x-amz-security-token",
            "x-amz-request-id", 
            "x-amzn-requestid",
            "x-amz-id-2"
        ]:
            if sensitive_header in response["headers"]:
                response["headers"][sensitive_header] = ["REDACTED"]
    return response

@pytest.fixture(scope="module")
def vcr_config():
    return {
        "filter_headers": [
            ("authorization", "AWS4-HMAC-SHA256 REDACTED"),
            ("x-amz-date", "REDACTED_DATE"),
            ("x-amz-security-token", "REDACTED_TOKEN"),
            ("x-amz-content-sha256", "REDACTED_CONTENT_HASH"),
        ],
        "filter_query_parameters": [
            ("X-Amz-Security-Token", "REDACTED"),
            ("X-Amz-Signature", "REDACTED"),
        ],
        "decode_compressed_response": True,
        "before_record_response": scrub_aws_credentials,
    }

@pytest.fixture(scope="session")
def instrument_langchain(reader, tracer_provider):
    langchain_instrumentor = LangChainInstrumentor()
    langchain_instrumentor.instrument(
        tracer_provider=tracer_provider
    )

    yield

    langchain_instrumentor.uninstrument()
    
@pytest.fixture(scope="function")
def instrument_no_content(
    tracer_provider
):
    os.environ.update(
        {OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: "False"}
    )

    instrumentor = LangChainInstrumentor()
    instrumentor.instrument(
        tracer_provider=tracer_provider,
    )
    yield instrumentor
    os.environ.pop(OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, None)
    instrumentor.uninstrument()


@pytest.fixture(scope="function")
def instrument_with_content(
    tracer_provider
):
    os.environ.update(
        {OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: "True"}
    )
    instrumentor = LangChainInstrumentor()
    instrumentor.instrument(
        tracer_provider=tracer_provider
    )

    yield instrumentor
    os.environ.pop(OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, None)
    instrumentor.uninstrument()
    
    
@pytest.fixture(scope="function")
def instrument_with_content_unsampled(
    span_exporter
):
    os.environ.update(
        {OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: "True"}
    )

    tracer_provider = TracerProvider(sampler=ALWAYS_OFF)
    tracer_provider.add_span_processor(SimpleSpanProcessor(span_exporter))

    instrumentor = LangChainInstrumentor()
    instrumentor.instrument(
        tracer_provider=tracer_provider
    )

    yield instrumentor
    os.environ.pop(OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, None)
    instrumentor.uninstrument()
    
