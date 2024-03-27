import logging
from typing import Optional
from unittest import mock

import pytest

from opentelemetry.instrumentation.logging import (  # pylint: disable=no-name-in-module
    DEFAULT_LOGGING_FORMAT,
    LoggingInstrumentor,
)
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import ProxyTracer, get_tracer

import sys
sys.path.insert(0, "../../../")
from handlers.opentelemetry_structlog.src.exporter import StructlogHandler


