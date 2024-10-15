from random import randint
from flask import Flask, request
import structlog
import sys

sys.path.insert(0, "../../..")
from handlers.opentelemetry_structlog.src.exporter import StructlogHandler
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (
    OTLPLogExporter,
)
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry._logs import set_logger_provider

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
structlog_handler = StructlogHandler(
    service_name="flask-structlog-demo",
    server_hostname="instance-1",
    exporter=OTLPLogExporter(insecure=True),
)
structlog_handler._logger_provider = logger_provider
structlog_logger = structlog.wrap_logger(
    structlog.get_logger(), processors=[structlog_handler]
)  # Add  StructlogHandler to the logger


app = Flask(__name__)


@app.route("/rolldice")
def roll_dice():
    player = request.args.get("player", default=None, type=str)
    result = str(roll())
    if player:
        structlog_logger.warning(
            "Player %s is rolling the dice: %s", player, result, level="warning"
        )
    else:
        structlog_logger.warning(
            "Anonymous player is rolling the dice: %s", result, level="warning"
        )
    return result


def roll():
    return randint(1, 6)
