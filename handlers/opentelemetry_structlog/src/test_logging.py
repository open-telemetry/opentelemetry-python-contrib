import pytest
from unittest.mock import Mock
from exporter import OpenTelemetryExporter
from opentelemetry.sdk._logs._internal.export import LogExporter
from datetime import datetime, timezone

# Test Initialization
@pytest.fixture
def otel_exporter():
    # Mock the LogExporter dependency
    mock_exporter = Mock(spec=LogExporter)
    # Instantiate the OpenTelemetryExporter with mock dependencies
    exporter = OpenTelemetryExporter("test_service", "test_host", mock_exporter)
    return exporter

def test_initialization(otel_exporter):
    assert otel_exporter._logger_provider is not None, "LoggerProvider should be initialized"
    assert otel_exporter._logger is not None, "Logger should be initialized"
    
def test_pre_process_adds_timestamp(otel_exporter):
    event_dict = {"event": "test_event"}
    processed_event = otel_exporter._pre_process(event_dict)
    assert "timestamp" in processed_event, "Timestamp should be added in pre-processing"

def test_post_process_formats_timestamp(otel_exporter):
    # Assuming the pre_process method has added a datetime object
    event_dict = {"timestamp": datetime.now(timezone.utc)}
    processed_event = otel_exporter._post_process(event_dict)
    assert isinstance(processed_event["timestamp"], str), "Timestamp should be formatted to string in ISO format"

def test_parse_exception(otel_exporter):
    # Mocking an exception event
    exception = (ValueError, ValueError("mock error"), None)
    event_dict = {"exception": exception}
    parsed_exception = otel_exporter._parse_exception(event_dict)
    assert parsed_exception["exception.type"] == "ValueError", "Exception type should be parsed"
    assert parsed_exception["exception.message"] == "mock error", "Exception message should be parsed"
    # Further assertions can be added for stack trace
    
def test_parse_timestamp(otel_exporter):
    # Assuming a specific datetime for consistency
    fixed_datetime = datetime(2020, 1, 1, tzinfo=timezone.utc)
    event_dict = {"timestamp": fixed_datetime}
    timestamp = otel_exporter._parse_timestamp(event_dict)
    expected_timestamp = 1577836800000000000  # Expected nanoseconds since epoch
    assert timestamp == expected_timestamp, "Timestamp should be correctly parsed to nanoseconds"

def test_call_method_processes_log_correctly(otel_exporter, mocker):
    mocker.patch.object(otel_exporter._logger, 'emit')
    event_dict = {"level": "info", "event": "test event", "timestamp": datetime.now(timezone.utc)}
    processed_event = otel_exporter(logger=None, name=None, event_dict=event_dict)

    otel_exporter._logger.emit.assert_called_once()
    assert "timestamp" in processed_event, "Processed event should contain a timestamp"
    # Add more assertions based on expected transformations and processing outcomes