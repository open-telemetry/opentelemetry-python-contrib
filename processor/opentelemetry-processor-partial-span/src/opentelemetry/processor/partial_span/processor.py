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

import datetime
import json
import logging
import threading
from typing import Optional, Union

from google.protobuf import json_format
from opentelemetry import context as context_api
from opentelemetry.exporter.otlp.proto.common.trace_encoder import encode_spans
from opentelemetry.processor.partial_span.peekable_queue import PeekableQueue
from opentelemetry.proto.trace.v1 import trace_pb2
from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor

DEFAULT_HEARTBEAT_INTERVAL_MILLIS = 5000
DEFAULT_INITIAL_HEARTBEAT_DELAY_MILLIS = 5000
DEFAULT_PROCESS_INTERVAL_MILLIS = 5000


class PartialSpanProcessor(SpanProcessor):
  """
  A SpanProcessor that emits logs on time interval called heartbeat during span lifetime and when span ends.
  Initial heartbeat can be delayed so processor does not become chatty (e.g. short lived spans).
  If heartbeat is delayed and span ends before initial heartbeat is emitted no logs are sent.
  Because of built-in limitation of logging module, the log body is used to serialize span data in json format.
  """

  HEARTBEAT_ATTRIBUTES = {
    "span.state": "heartbeat",
    "log.body.type": "json/v1",
  }
  END_ATTRIBUTES = {
    "span.state": "ended",
    "log.body.type": "json/v1",
  }
  WORKER_THREAD_NAME = "OtelPartialSpanProcessor"

  def __init__(self, logger: logging.Logger,
      heartbeat_interval_millis: int = DEFAULT_HEARTBEAT_INTERVAL_MILLIS,
      initial_heartbeat_delay_millis: int = DEFAULT_INITIAL_HEARTBEAT_DELAY_MILLIS,
      process_interval_millis: int = DEFAULT_PROCESS_INTERVAL_MILLIS
  ) -> None:
    self.validate_parameters(logger, heartbeat_interval_millis,
                             initial_heartbeat_delay_millis,
                             process_interval_millis)
    self.logger = logger
    self.heartbeat_interval_millis = heartbeat_interval_millis
    self.initial_heartbeat_delay_millis = initial_heartbeat_delay_millis
    self.process_interval_millis = process_interval_millis

    self.active_spans: dict[str, Union[Span, ReadableSpan]] = {}
    self.delayed_heartbeat_spans: PeekableQueue[tuple[int, datetime.datetime]] = \
      PeekableQueue()
    self.delayed_heartbeat_spans_lookup: set[int] = set()
    self.ready_heartbeat_spans: PeekableQueue[
      tuple[int, datetime.datetime]] = PeekableQueue()

    self.lock = threading.Lock()

    self.done = False
    self.condition = threading.Condition(threading.Lock())
    self.worker_thread = threading.Thread(name=self.WORKER_THREAD_NAME,
                                          target=self.worker, daemon=True)
    self.worker_thread.start()

  @staticmethod
  def validate_parameters(logger, heartbeat_interval_millis,
      initial_heartbeat_delay_millis, process_interval_millis):
    if logger is None:
      msg = "logger must not be None"
      raise ValueError(msg)

    if heartbeat_interval_millis <= 0:
      msg = "heartbeat_interval_millis must be greater than 0"
      raise ValueError(msg)

    if initial_heartbeat_delay_millis < 0:
      msg = "initial_heartbeat_delay_millis must be greater or equal to 0"
      raise ValueError(msg)

    if process_interval_millis <= 0:
      msg = "process_interval_millis must be greater than 0"
      raise ValueError(msg)

  def worker(self) -> None:
    while not self.done:
      with self.condition:
        self.condition.wait(self.process_interval_millis / 1000)
        if self.done:
          break

        self.process_delayed_heartbeat_spans()
        self.process_ready_heartbeat_spans()

  def process_delayed_heartbeat_spans(self) -> None:
    spans_to_be_logged = []
    with (self.lock):
      now = datetime.datetime.now()
      while True:
        if self.delayed_heartbeat_spans.empty():
          break

        (span_id, next_heartbeat_time) = self.delayed_heartbeat_spans.peek()
        if next_heartbeat_time > now:
          break

        self.delayed_heartbeat_spans_lookup.discard(span_id)
        self.delayed_heartbeat_spans.get()

        span = self.active_spans.get(span_id)
        if span:
          spans_to_be_logged.append(span)

          next_heartbeat_time = now + datetime.timedelta(
            milliseconds=self.heartbeat_interval_millis)
          self.ready_heartbeat_spans.put((span_id, next_heartbeat_time))

    for span in spans_to_be_logged:
      self.logger.info(msg=self.serialize_span_to_json(span),
                       extra=self.HEARTBEAT_ATTRIBUTES)

  def process_ready_heartbeat_spans(self) -> None:
    spans_to_be_logged = []
    now = datetime.datetime.now()
    with self.lock:
      while True:
        if self.ready_heartbeat_spans.empty():
          break

        (span_id, next_heartbeat_time) = self.ready_heartbeat_spans.peek()
        if next_heartbeat_time > now:
          break

        self.ready_heartbeat_spans.get()

        span = self.active_spans.get(span_id)
        if span:
          spans_to_be_logged.append(span)

          next_heartbeat_time = now + datetime.timedelta(
            milliseconds=self.heartbeat_interval_millis)
          self.ready_heartbeat_spans.put((span_id, next_heartbeat_time))

    for span in spans_to_be_logged:
      self.logger.info(msg=self.serialize_span_to_json(span),
                       extra=self.HEARTBEAT_ATTRIBUTES)

  def on_start(self, span: "Span",
      parent_context: Optional[context_api.Context] = None) -> None:
    with self.lock:
      self.active_spans[span.context.span_id] = span
      self.delayed_heartbeat_spans_lookup.add(span.context.span_id)

      next_heartbeat_time = datetime.datetime.now() + datetime.timedelta(
        milliseconds=self.initial_heartbeat_delay_millis)
      self.delayed_heartbeat_spans.put(
        (span.context.span_id, next_heartbeat_time))

  def on_end(self, span: ReadableSpan) -> None:
    is_delayed_heartbeat_pending = False
    with self.lock:
      self.active_spans.pop(span.context.span_id)

      if span.context.span_id in self.delayed_heartbeat_spans_lookup:
        is_delayed_heartbeat_pending = True
        self.delayed_heartbeat_spans_lookup.remove(span.context.span_id)

    if is_delayed_heartbeat_pending:
      return

    self.logger.info(msg=self.serialize_span_to_json(span),
                     extra=self.END_ATTRIBUTES)

  def shutdown(self) -> None:
    self.done = True
    with self.condition:
      self.condition.notify_all()
    self.worker_thread.join()

  @staticmethod
  def serialize_span_to_json(span: Union[Span, ReadableSpan]) -> str:
    span_context = span.get_span_context()
    parent = span.parent

    enc_spans = encode_spans([span]).resource_spans
    traces_data = trace_pb2.TracesData()
    traces_data.resource_spans.extend(enc_spans)
    serialized_traces_data = json_format.MessageToJson(traces_data)

    # FIXME/HACK replace serialized traceId, spanId, and parentSpanId (if present) values as string comparison
    # possible issue is when there are multiple spans in the same trace.
    # currently that should not be the case.
    # trace_id, span_id and parentSpanId are stored as int.
    # when serializing it gets serialized to bytes.
    # that is not inline specification.
    traces = json.loads(serialized_traces_data)
    for resource_span in traces.get("resourceSpans", []):
      for scope_span in resource_span.get("scopeSpans", []):
        for span in scope_span.get("spans", []):
          span["traceId"] = hex(span_context.trace_id)[2:]
          span["spanId"] = hex(span_context.span_id)[2:]
          if parent:
            span["parentSpanId"] = hex(parent.span_id)[2:]

    return json.dumps(traces, separators=(",", ":"))
