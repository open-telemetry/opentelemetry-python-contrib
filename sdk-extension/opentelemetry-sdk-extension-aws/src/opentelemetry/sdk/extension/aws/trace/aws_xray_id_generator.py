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

"""
Installation
------------

::

    pip install opentelemetry-sdk-extension-aws

AWS X-Ray IDs Generator
-----------------------

The **AWS X-Ray IDs Generator** provides a custom IDs Generator to make
traces generated using the OpenTelemetry SDKs `TracerProvider` compatible
with the AWS X-Ray backend service `trace ID format`_.

Usage
-----

Configure the OTel SDK TracerProvider with the provided custom IDs Generator to
make spans compatible with the AWS X-Ray backend tracing service.

Install the OpenTelemetry SDK package.

::

    pip install opentelemetry-sdk

Next, use the provided `AwsXRayIdGenerator` to initialize the `TracerProvider`.

.. code-block:: python

    import opentelemetry.trace as trace
    from opentelemetry.sdk.extension.aws.trace import AwsXRayIdGenerator
    from opentelemetry.sdk.trace import TracerProvider

    trace.set_tracer_provider(
        TracerProvider(id_generator=AwsXRayIdGenerator())
    )

API
---
.. _trace ID format: https://docs.aws.amazon.com/xray/latest/devguide/xray-api-sendingdata.html#xray-api-traceids
"""

import time
import random


class AwsXRayIdGenerator():
    """Generates tracing IDs compatible with the AWS X-Ray tracing service.
    See: https://docs.aws.amazon.com/xray/latest/devguide/xray-api-sendingdata.html#xray-api-traceids
    See Same implementation in Javascript: https://github.com/aws-observability/aws-otel-js/tree/main/packages/opentelemetry-id-generator-aws-xray
    """
    TIME = time
    TRACE_ID_LENGTH = 32
    SPAN_ID_LENGTH = 16

    # Ex: 0c6d1c759808e783
    def generate_span_id(self) -> str:
        return (hex(random.getrandbits(88))[2:])[:self.SPAN_ID_LENGTH]

    # Ex: 6068d890e80ef8ae6323f667558381bd
    def generate_trace_id(self) -> str:
        stamp8 = hex(int(self.TIME.time()))[2:]
        random24 = hex(random.getrandbits(116))[2:]
        return (stamp8 + random24)[:self.TRACE_ID_LENGTH]
