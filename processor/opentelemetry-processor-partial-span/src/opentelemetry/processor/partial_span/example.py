# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
from time import sleep

from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.processor.partial_span import PartialSpanProcessor
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs import LoggingHandler
from opentelemetry.sdk._logs.export import SimpleLogRecordProcessor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry import trace

resource = Resource(attributes={
  SERVICE_NAME: "my-service"
})
logger_provider = LoggerProvider(resource=resource)

otlp_exporter = OTLPLogExporter(endpoint="http://localhost:4318/v1/logs")
log_processor = SimpleLogRecordProcessor(otlp_exporter)
logger_provider.add_log_record_processor(log_processor)

otel_handler = LoggingHandler(level=logging.INFO,
                              logger_provider=logger_provider)

logger = logging.getLogger("example")
logger.setLevel(logging.INFO)
logger.addHandler(otel_handler)

tracer_provider = TracerProvider()
tracer_provider.add_span_processor(
  PartialSpanProcessor(logger=logger, heartbeat_interval_millis=1000,
                       initial_heartbeat_delay_millis=1000,
                       process_interval_millis=1000))
trace.set_tracer_provider(tracer_provider)
tracer = trace.get_tracer(__name__)

with tracer.start_as_current_span("example-span"):
  sleep(5)
