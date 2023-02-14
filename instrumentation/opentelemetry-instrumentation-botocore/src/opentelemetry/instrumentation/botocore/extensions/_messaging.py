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
import json
import logging
from typing import Any, List, Mapping, MutableMapping, Optional

from opentelemetry.propagate import extract, get_global_textmap, inject
from opentelemetry.propagators.textmap import CarrierT, Getter, Setter
from opentelemetry.trace.propagation import get_current_span
from opentelemetry.trace.span import INVALID_SPAN, Span

_logger = logging.getLogger(__name__)

_MAX_MESSAGE_ATTRIBUTES = 10


class MessageAttributesSetter(Setter[CarrierT]):
    def set(self, carrier: CarrierT, key: str, value: str):
        carrier[key] = {
            "DataType": "String",
            "StringValue": value,
        }


class MessageAttributesGetter(Getter[CarrierT]):
    def get(self, carrier: CarrierT, key: str) -> Optional[List[str]]:
        attr = carrier and carrier.get(key)
        if not isinstance(attr, Mapping):
            return None

        value = attr.get("StringValue") or attr.get("Value")
        return [value] if value else None

    def keys(self, carrier: CarrierT) -> List[str]:
        return [] if not isinstance(carrier, Mapping) else carrier.keys()


message_attributes_setter = MessageAttributesSetter()
message_attributes_getter = MessageAttributesGetter()


def inject_span_into_message(message: MutableMapping[str, Any]):
    message["MessageAttributes"] = inject_propagation_context(
        message.get("MessageAttributes")
    )


def inject_propagation_context(
    carrier: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    if carrier is None:
        carrier = {}

    fields = get_global_textmap().fields
    if len(carrier.keys()) + len(fields) <= _MAX_MESSAGE_ATTRIBUTES:
        inject(carrier, setter=message_attributes_setter)
    else:
        _logger.warning(
            "botocore instrumentation: cannot set context propagation on "
            "SQS/SNS message due to maximum amount of MessageAttributes"
        )

    return carrier


def extract_propagation_context(
    message: Mapping[str, Any], extract_from_payload=False
) -> Span:
    carrier = message.get("MessageAttributes")
    if carrier:
        ctx = extract(carrier, getter=message_attributes_getter)
        span = get_current_span(ctx)
        if span.get_span_context().is_valid:
            return span

    if not extract_from_payload:
        return INVALID_SPAN

    try:
        msg_body = json.loads(message.get("Body") or "")
    except json.JSONDecodeError:
        return INVALID_SPAN

    if not isinstance(msg_body, Mapping):
        return INVALID_SPAN

    carrier = msg_body.get("MessageAttributes")
    if not carrier:
        return INVALID_SPAN

    ctx = extract(carrier, getter=message_attributes_getter)
    return get_current_span(ctx)
