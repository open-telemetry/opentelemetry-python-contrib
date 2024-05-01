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

