# OpenTelemetry Python `structlog` Handler Example with Docker
This is a demo for the custom structlog handler implemented for OpenTelemetry. Overall, this example runs a basic Flask application with Docker to demonstrate an example application that uses OpenTelemetry logging with Python's logging library structlog. This example is scalable to other software systems that require the use of the structlog library for logging.

Note: This example is adapted from OpenTelemetry's [Getting Started Tutorial for Python](https://opentelemetry.io/docs/languages/python/getting-started/) guide and OpenTelemetry's [example for logs](https://github.com/open-telemetry/opentelemetry-python/blob/main/docs/examples/logs/README.rst) code.

## Prerequisites
Python 3

## Installation
Prior to building the example application, set up the directory and virtual environment:
```
mkdir otel-structlog-example
cd otel-structlog-example
python3 -m venv venv
source ./venv/bin/activate
```

After activating the virtual environment `venv`, install flask and structlog.
```
pip install flask
pip install structlog
pip install opentelemetry-exporter-otlp
```

### Create and Launch HTTP Server
Now that the environment is set up, create an `app.py` flask application. This is a basic example that uses the structlog Python logging library for OpenTelemetry logging instead of the standard Python logging library. 

Notice the importance of the following imports for using the structlog handler: `import structlog` and `from handlers.opentelemetry_structlog.src.exporter import StructlogHandler`.

```
from random import randint
from flask import Flask, request
import structlog
import sys
sys.path.insert(0, '../../..')
from handlers.opentelemetry_structlog.src.exporter import StructlogHandler
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (
    OTLPLogExporter,
)
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource

logger_provider = LoggerProvider(
    resource=Resource.create(
        {
            "service.name": "shoppingcart",
            "service.instance.id": "instance-12",
        }
    ),
)
set_logger_provider(logger_provider)

# Replace the standard logging configuration with structlog
structlog_handler = StructlogHandler(service_name="flask-structlog-demo", server_hostname="instance-1", exporter=OTLPLogExporter(insecure=True)) 
structlog_handler._logger_provider = logger_provider
structlog_logger = structlog.wrap_logger(structlog.get_logger(), processors=[structlog_handler])  # Add  StructlogHandler to the logger

app = Flask(__name__)

@app.route("/rolldice")
def roll_dice():
    player = request.args.get('player', default=None, type=str)
    result = str(roll())
    if player:
        structlog_logger.warning("Player %s is rolling the dice: %s", player, result, level="warning")
    else:
        structlog_logger.warning("Anonymous player is rolling the dice: %s", result, level="warning")
    return result


def roll():
    return randint(1, 6)
```

Run the application on port 8080 with the following flask command and open [http://localhost:8080/rolldice](http://localhost:8080/rolldice) in your web browser to ensure it is working. 

```
flask run -p 8080
```

However, do not be alarmed if you receive these errors since Docker is not yet set up to export the logs:
```
Transient error StatusCode.UNAVAILABLE encountered while exporting logs to localhost:4317, retrying in 1s.
Transient error StatusCode.UNAVAILABLE encountered while exporting logs to localhost:4317, retrying in 2s.
Transient error StatusCode.UNAVAILABLE encountered while exporting logs to localhost:4317, retrying in 4s.
...
```

## Run with Docker

To serve the application on Docker, first create the `otel-collector-config.yaml` file locally in the application's repository.
```
# otel-collector-config.yaml
receivers:
  otlp:
    protocols:
      grpc:

processors:
  batch:

exporters:
  logging:
    verbosity: detailed

service:
    pipelines:
        logs:
            receivers: [otlp]
            processors: [batch]
            exporters: [logging]
```

Next, start the Docker container:
```
docker run \
    -p 4317:4317 \
    -v $(pwd)/otel-collector-config.yaml:/etc/otelcol-contrib/config.yaml \
    otel/opentelemetry-collector-contrib:latest
```

And lastly, run the basic application with flask:
```
flask run -p 8080
```

Here is some example output:
```
 * Debug mode: off
WARNING: This is a development server. Do not use it in a production deployment. Use a production WSGI server instead.
 * Running on http://127.0.0.1:8080
Press CTRL+C to quit
2024-04-28 23:15:22 [warning  ] Anonymous player is rolling the dice: 1
127.0.0.1 - - [28/Apr/2024 23:15:22] "GET /rolldice HTTP/1.1" 200 -
2024-04-28 23:15:27 [warning  ] Anonymous player is rolling the dice: 6
127.0.0.1 - - [28/Apr/2024 23:15:27] "GET /rolldice HTTP/1.1" 200 -
2024-04-28 23:15:28 [warning  ] Anonymous player is rolling the dice: 3
127.0.0.1 - - [28/Apr/2024 23:15:28] "GET /rolldice HTTP/1.1" 200 -
2024-04-28 23:15:29 [warning  ] Anonymous player is rolling the dice: 4
127.0.0.1 - - [28/Apr/2024 23:15:29] "GET /rolldice HTTP/1.1" 200 -
2024-04-28 23:15:29 [warning  ] Anonymous player is rolling the dice: 1
127.0.0.1 - - [28/Apr/2024 23:15:29] "GET /rolldice HTTP/1.1" 200 -
2024-04-28 23:15:30 [warning  ] Anonymous player is rolling the dice: 2
127.0.0.1 - - [28/Apr/2024 23:15:30] "GET /rolldice HTTP/1.1" 200 -
2024-04-28 23:15:31 [warning  ] Anonymous player is rolling the dice: 3
127.0.0.1 - - [28/Apr/2024 23:15:31] "GET /rolldice HTTP/1.1" 200 -
2024-04-28 23:16:14 [warning  ] Anonymous player is rolling the dice: 4
127.0.0.1 - - [28/Apr/2024 23:16:14] "GET /rolldice HTTP/1.1" 200 -
```


## Contributors
Caroline Gilbert: [carolincgilbert](https://github.com/carolinecgilbert)
