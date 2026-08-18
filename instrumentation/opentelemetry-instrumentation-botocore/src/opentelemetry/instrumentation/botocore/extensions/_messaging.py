# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import logging
from typing import Any, MutableMapping

from opentelemetry.propagate import get_global_textmap, inject
from opentelemetry.propagators.textmap import CarrierT, Setter

_logger = logging.getLogger(__name__)

_MAX_MESSAGE_ATTRIBUTES = 10


class MessageAttributesSetter(Setter[CarrierT]):
    def set(self, carrier: CarrierT, key: str, value: str):
        carrier[key] = {
            "DataType": "String",
            "StringValue": value,
        }


message_attributes_setter = MessageAttributesSetter()


def inject_propagation_context(
    carrier: MutableMapping[str, Any],
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
