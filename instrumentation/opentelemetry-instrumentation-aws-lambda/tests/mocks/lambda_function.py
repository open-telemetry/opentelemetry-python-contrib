# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import json

from opentelemetry import baggage as baggage_api


def handler(event, context):
    baggage_content = dict(baggage_api.get_all().items())
    return json.dumps({"baggage_content": baggage_content})


def rest_api_handler(event, context):
    return {"statusCode": 200, "body": "200 ok"}


def handler_exc(event, context):
    # pylint: disable=broad-exception-raised
    raise Exception("500 internal server error")
