# OpenTelemetry Python `loguru` Handler Example with Docker
This is a demo for the custom loguru handler implemented for OpenTelemetry. Overall, this example runs a basic Flask application with Docker to demonstrate an example application that uses OpenTelemetry logging with Python's logging library loguru. This example is scalable to other software systems that require the use of the loguru library for logging.

Note: This example is adapted from OpenTelemetry's [Getting Started Tutorial for Python](https://opentelemetry.io/docs/languages/python/getting-started/) guide and OpenTelemetry's [example for logs](https://github.com/open-telemetry/opentelemetry-python/blob/main/docs/examples/logs/README.rst) code.

## Prerequisites
Python 3

## Installation
Prior to building the example application, set up the directory and virtual environment:
```
mkdir otel-loguru-example
cd otel-loguru-example
python3 -m venv venv
source ./venv/bin/activate
```

After activating the virtual environment `venv`, install flask and loguru.
```
pip install flask
pip install loguru
pip install opentelemetry-exporter-otlp
```

### Create and Launch HTTP Server
Now that the environment is set up, create an `app.py` flask application. This is a basic example that uses the loguru Python logging library for OpenTelemetry logging instead of the standard Python logging library. 

Notice the importance of the following imports for using the loguru handler: `import loguru` and `from handlers.opentelemetry_loguru.src.exporter import LoguruHandler`.

```
from random import randint
from flask import Flask, request
from loguru import logger as loguru_logger
import sys
sys.path.insert(0, '../../..')
from handlers.opentelemetry_loguru.src.exporter import LoguruHandler

from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (
    OTLPLogExporter,
)
from opentelemetry.sdk._logs import LoggerProvider
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

# Replace the standard logging configuration with Loguru
loguru_handler = LoguruHandler(service_name="flask-loguru-demo", server_hostname="instance-1", exporter=OTLPLogExporter(insecure=True)) 
loguru_logger.add(loguru_handler.sink)  # Add  LoguruHandler to the logger

app = Flask(__name__)

@app.route("/rolldice")
def roll_dice():
    player = request.args.get('player', default=None, type=str)
    result = str(roll())
    if player:
        loguru_logger.warning("Player is rolling the dice: num")
    else:
        loguru_logger.warning("Anonymous player is rolling the dice: num")
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

```


## Contributors
Caroline Gilbert: [carolincgilbert](https://github.com/carolinecgilbert)
