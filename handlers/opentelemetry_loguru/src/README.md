# Loguru Handler for OpenTelemetry

This project provides a Loguru handler for OpenTelemetry applications. The handler converts Loguru logs into the OpenTelemetry Logs Protocol (OTLP) format for export to a collector.

## Usage

To use the Loguru handler in your OpenTelemetry application, follow these steps:

1. Import the necessary modules:

```python
import loguru
from handlers.opentelemetry_loguru.src.exporter import LoguruHandler
from opentelemetry.sdk._logs._internal.export import LogExporter
from opentelemetry.sdk.resources import Resource
```

2. Initialize the LoguruHandler with your service name, server hostname, and LogExporter instance:

```python
service_name = "my_service"
server_hostname = "my_server"
exporter = LogExporter()  # Initialize your LogExporter instance
handler = LoguruHandler(service_name, server_hostname, exporter)
```

3. Add the handler to your Loguru logger:

```python
logger = loguru.logger
logger.add(handler.sink)
```

4. Use the logger as usual with Loguru:

```python
logger.warning("This is a test log message.")
```
## OpenTelemetry Application Example with Handler
See the loguru handler demo in the examples directory of this repository for a step-by-step guide on using the handler in an OpenTelemetry application.

## Customization

The LoguruHandler supports customization through its constructor parameters:

- `service_name`: The name of your service.
- `server_hostname`: The hostname of the server where the logs originate.
- `exporter`: An instance of your LogExporter for exporting logs to a collector.

## Notes

- This handler automatically converts Loguru logs into the OTLP format for compatibility with OpenTelemetry.
- It extracts attributes from Loguru logs and maps them to OpenTelemetry attributes for log records.
