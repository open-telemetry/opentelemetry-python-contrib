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

import abc
import inspect
import json
import logging
from typing import Any, Dict, MutableMapping

from opentelemetry.propagate import inject
from opentelemetry.instrumentation.botocore.extensions.types import (
    _AttributeMapT,
    _AwsSdkCallContext,
    _AwsSdkExtension,
    _BotocoreInstrumentorContext,
)
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import SpanKind
from opentelemetry.trace.span import Span

_logger = logging.getLogger(__name__)

################################################################################
# Kinesis operations
################################################################################


class _KinesisOperation(abc.ABC):
    @classmethod
    @abc.abstractmethod
    def operation_name(cls) -> str:
        pass

    @classmethod
    def span_kind(cls) -> SpanKind:
        return SpanKind.CLIENT

    @classmethod
    def extract_attributes(
        cls, call_context: _AwsSdkCallContext, attributes: _AttributeMapT
    ):
        pass

    @classmethod
    def before_service_call(cls, call_context: _AwsSdkCallContext, span: Span):
        pass


class _OpPutRecord(_KinesisOperation):
    @classmethod
    def operation_name(cls) -> str:
        return "PutRecord"

    @classmethod
    def span_kind(cls) -> SpanKind:
        return SpanKind.PRODUCER

    @classmethod
    def _extract_stream_name(cls, call_context: _AwsSdkCallContext) -> str:
        stream_name = call_context.params.get("StreamName")
        if stream_name:
            return stream_name

        stream_arn = call_context.params.get("StreamARN", "")
        if "/" in stream_arn:
            return stream_arn.split("/", 1)[-1]

        return "unknown"

    @classmethod
    def extract_attributes(
        cls, call_context: _AwsSdkCallContext, attributes: _AttributeMapT
    ):
        stream_name = cls._extract_stream_name(call_context)
        call_context.span_name = f"{stream_name} send"
        attributes[SpanAttributes.MESSAGING_DESTINATION_NAME] = stream_name

    @classmethod
    def before_service_call(cls, call_context: _AwsSdkCallContext, span: Span):
        cls._inject_span_into_entry(call_context.params)

    @classmethod
    def _inject_span_into_entry(cls, entry: MutableMapping[str, Any]):
        """Inject trace context into the Data JSON payload."""
        data = entry.get("Data")
        if data is None:
            return
        use_bytes = False
        try:
            if isinstance(data, bytes):
                data_str = data.decode("utf-8")
                use_bytes = True
            else:
                data_str = data
            data_dict = json.loads(data_str)
        except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
            _logger.debug(
                "botocore instrumentation: failed to parse Kinesis Data as JSON"
            )
            return

        inject(data_dict)
        data_dump = json.dumps(data_dict)
        data_bytes = data_dump.encode("utf-8")
        if len(data_bytes) > 1_048_576:
            _logger.debug(
                "botocore instrumentation: skipping Kinesis context injection, "
                "record would exceed 1MB limit"
            )
            return
        entry["Data"] = data_bytes if use_bytes else data_dump


class _OpPutRecords(_OpPutRecord):
    @classmethod
    def operation_name(cls) -> str:
        return "PutRecords"

    @classmethod
    def before_service_call(cls, call_context: _AwsSdkCallContext, span: Span):
        for record in call_context.params.get("Records", []):
            cls._inject_span_into_entry(record)


################################################################################
# Kinesis extension
################################################################################

_OPERATION_MAPPING: Dict[str, _KinesisOperation] = {
    op.operation_name(): op
    for op in globals().values()
    if inspect.isclass(op)
    and issubclass(op, _KinesisOperation)
    and not inspect.isabstract(op)
}


class _KinesisExtension(_AwsSdkExtension):
    def __init__(self, call_context: _AwsSdkCallContext):
        super().__init__(call_context)
        self._op = _OPERATION_MAPPING.get(call_context.operation)
        if self._op:
            call_context.span_kind = self._op.span_kind()

    def extract_attributes(self, attributes: _AttributeMapT):
        attributes[SpanAttributes.MESSAGING_SYSTEM] = "aws.kinesis"

        if self._op:
            self._op.extract_attributes(self._call_context, attributes)

    def before_service_call(
        self, span: Span, instrumentor_context: _BotocoreInstrumentorContext
    ):
        if self._op:
            self._op.before_service_call(self._call_context, span)
