# Structlog Handler for OpenTelemetry
This project provides a Structlog handler for OpenTelemetry applications. The handler converts Structlog logs into the OpenTelemetry Logs Protocol (OTLP) format for export to a collector.

## Usage

To use the Structlog handler in your OpenTelemetry application, follow these steps:

1. Import the necessary modules:

```python
import structlog
from opentelemetry.sdk._logs._internal.export import LogExporter
from opentelemetry.sdk.resources import Resource
from handlers.opentelemetry_structlog.src.exporter import StructlogHandler
```

2. Initialize the StructlogHandler with your service name, server hostname, and LogExporter instance:

```python
service_name = "my_service"
server_hostname = "my_server"
exporter = LogExporter()  # Initialize your LogExporter instance
handler = StructlogHandler(service_name, server_hostname, exporter)
```

3. Add the handler to your Structlog logger:

```python
structlog.configure(
    processors=[structlog.processors.JSONRenderer()],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
    context_class=dict,
    **handler.wrap_for_structlog(),
)
```

4. Use the logger as usual with Structlog:

```python
logger = structlog.get_logger()
logger.info("This is a test log message.")
```
## OpenTelemetry Application Example with Handler
See the structlog handler demo in the examples directory of this repository for a step-by-step guide on using the handler in an OpenTelemetry application.

## Customization

The StructlogHandler supports customization through its constructor parameters:

- `service_name`: The name of your service.
- `server_hostname`: The hostname of the server where the logs originate.
- `exporter`: An instance of your LogExporter for exporting logs to a collector.

## Notes

- This handler automatically converts the `timestamp` key in the `event_dict` to ISO 8601 format for better compatibility.
- It performs operations similar to `structlog.processors.ExceptionRenderer`, so avoid using `ExceptionRenderer` in the same pipeline.
```
