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
AWS X-Ray Propagator
--------------------

The **AWS X-Ray Propagator** provides a propagator that when used, adds a `trace
header`_ to outgoing traces that is compatible with the AWS X-Ray backend
service. This allows the trace context to be propagated when a trace spans
multiple AWS services.

The same propagator setup is used to extract a context sent by external systems
so that child span have the correct parent context.

**NOTE**: Because the parent context parsed from the ``X-Amzn-Trace-Id`` header
assumes the context is _not_ sampled by default, users should make sure to add
``Sampled=1`` to their ``X-Amzn-Trace-Id`` headers so that the child spans are
sampled.

Usage
-----

Use the provided AWS X-Ray Propagator to inject the necessary context into
traces sent to external systems.

This can be done by either setting this environment variable:

::

    export OTEL_PROPAGATORS = xray


Or by setting this propagator in your instrumented application:

.. code-block:: python

    from opentelemetry.propagate import set_global_textmap
    from opentelemetry.propagators.aws import AwsXRayPropagator

    set_global_textmap(AwsXRayPropagator())

API
---
.. _trace header: https://docs.aws.amazon.com/xray/latest/devguide/xray-concepts.html#xray-concepts-tracingheader
"""

import logging
import typing
from os import environ

from opentelemetry import baggage, trace
from opentelemetry.context import Context
from opentelemetry.propagators.textmap import (
    CarrierT,
    Getter,
    Setter,
    TextMapPropagator,
    default_getter,
    default_setter,
)

TRACE_HEADER_KEY = "X-Amzn-Trace-Id"
AWS_TRACE_HEADER_ENV_KEY = "_X_AMZN_TRACE_ID"
KV_PAIR_DELIMITER = ";"
KEY_AND_VALUE_DELIMITER = "="

TRACE_ID_KEY = "Root"
TRACE_ID_LENGTH = 35
TRACE_ID_VERSION = "1"
TRACE_ID_DELIMITER = "-"
TRACE_ID_DELIMITER_INDEX_1 = 1
TRACE_ID_DELIMITER_INDEX_2 = 10
TRACE_ID_FIRST_PART_LENGTH = 8

PARENT_ID_KEY = "Parent"
PARENT_ID_LENGTH = 16

SAMPLED_FLAG_KEY = "Sampled"
SAMPLED_FLAG_LENGTH = 1
IS_SAMPLED = "1"
NOT_SAMPLED = "0"

LINEAGE_KEY = "Lineage"
LINEAGE_DELIMITER = ":"
LINEAGE_MAX_LENGTH = 18
LINEAGE_MIN_LENGTH = 12
LINEAGE_HASH_LENGTH = 8
LINEAGE_MAX_COUNTER1 = 32767
LINEAGE_MAX_COUNTER2 = 255
LINEAGE_MIN_COUNTER = 0
INVALID_LINEAGE_HEADER = "-1:11111111:0"


_logger = logging.getLogger(__name__)


class AwsParseTraceHeaderError(Exception):
    def __init__(self, message):
        super().__init__()
        self.message = message


class AwsXRayPropagator(TextMapPropagator):
    """Propagator for the AWS X-Ray Trace Header propagation protocol.

    See:
    https://docs.aws.amazon.com/xray/latest/devguide/xray-concepts.html#xray-concepts-tracingheader
    """

    # AWS

    def extract(
        self,
        carrier: CarrierT,
        context: typing.Optional[Context] = None,
        getter: Getter[CarrierT] = default_getter,
    ) -> Context:
        if context is None:
            context = Context()

        trace_header_list = getter.get(carrier, TRACE_HEADER_KEY)

        if not trace_header_list or len(trace_header_list) != 1:
            return context

        trace_header = trace_header_list[0]

        if not trace_header:
            return context

        try:
            (trace_id, span_id, sampled, lineage) = (
                AwsXRayPropagator._extract_span_properties(trace_header)
            )
        except AwsParseTraceHeaderError as err:
            _logger.debug(err.message)
            return context

        options = 0
        if sampled:
            options |= trace.TraceFlags.SAMPLED

        span_context = trace.SpanContext(
            trace_id=trace_id,
            span_id=span_id,
            is_remote=True,
            trace_flags=trace.TraceFlags(options),
            trace_state=trace.TraceState(),
        )

        if not span_context.is_valid:
            _logger.debug(
                "Invalid Span Extracted. Inserting INVALID span into provided context."
            )
            return context

        if lineage is not INVALID_LINEAGE_HEADER:
            context.update(baggage.set_baggage(LINEAGE_KEY, lineage, context=context))

        return trace.set_span_in_context(
            trace.NonRecordingSpan(span_context), context=context
        )

    @staticmethod
    def _extract_span_properties(trace_header):
        trace_id = trace.INVALID_TRACE_ID
        span_id = trace.INVALID_SPAN_ID
        sampled = False
        lineage = INVALID_LINEAGE_HEADER

        for kv_pair_str in trace_header.split(KV_PAIR_DELIMITER):
            try:
                key_str, value_str = kv_pair_str.split(KEY_AND_VALUE_DELIMITER)
                key, value = key_str.strip(), value_str.strip()
            except ValueError as ex:
                raise AwsParseTraceHeaderError(
                    (
                        "Error parsing X-Ray trace header. Invalid key value pair: %s. Returning INVALID span context.",
                        kv_pair_str,
                    )
                ) from ex
            if key == TRACE_ID_KEY:
                if not AwsXRayPropagator._validate_trace_id(value):
                    raise AwsParseTraceHeaderError(
                        (
                            "Invalid TraceId in X-Ray trace header: '%s' with value '%s'. Returning INVALID span context.",
                            TRACE_HEADER_KEY,
                            trace_header,
                        )
                    )

                try:
                    trace_id = AwsXRayPropagator._parse_trace_id(value)
                except ValueError as ex:
                    raise AwsParseTraceHeaderError(
                        (
                            "Invalid TraceId in X-Ray trace header: '%s' with value '%s'. Returning INVALID span context.",
                            TRACE_HEADER_KEY,
                            trace_header,
                        )
                    ) from ex
            elif key == PARENT_ID_KEY:
                if not AwsXRayPropagator._validate_span_id(value):
                    raise AwsParseTraceHeaderError(
                        (
                            "Invalid ParentId in X-Ray trace header: '%s' with value '%s'. Returning INVALID span context.",
                            TRACE_HEADER_KEY,
                            trace_header,
                        )
                    )

                try:
                    span_id = AwsXRayPropagator._parse_span_id(value)
                except ValueError as ex:
                    raise AwsParseTraceHeaderError(
                        (
                            "Invalid TraceId in X-Ray trace header: '%s' with value '%s'. Returning INVALID span context.",
                            TRACE_HEADER_KEY,
                            trace_header,
                        )
                    ) from ex
            elif key == SAMPLED_FLAG_KEY:
                if not AwsXRayPropagator._validate_sampled_flag(value):
                    raise AwsParseTraceHeaderError(
                        (
                            "Invalid Sampling flag in X-Ray trace header: '%s' with value '%s'. Returning INVALID span context.",
                            TRACE_HEADER_KEY,
                            trace_header,
                        )
                    )

                sampled = AwsXRayPropagator._parse_sampled_flag(value)

            elif key == LINEAGE_KEY:
                lineage = AwsXRayPropagator._parse_lineage_header(value)
                if not AwsXRayPropagator._is_valid_lineage(lineage):
                    _logger.debug(
                        "Invalid Lineage in X-Ray trace header: '%s' with value '%s'. Returning trace header with no lineage",
                        TRACE_HEADER_KEY,
                        lineage,
                    )

                    lineage = INVALID_LINEAGE_HEADER

        return trace_id, span_id, sampled, lineage

    @staticmethod
    def _validate_trace_id(trace_id_str):
        return (
            len(trace_id_str) == TRACE_ID_LENGTH
            and trace_id_str.startswith(TRACE_ID_VERSION)
            and trace_id_str[TRACE_ID_DELIMITER_INDEX_1] == TRACE_ID_DELIMITER
            and trace_id_str[TRACE_ID_DELIMITER_INDEX_2] == TRACE_ID_DELIMITER
        )

    @staticmethod
    def _parse_trace_id(trace_id_str):
        timestamp_subset = trace_id_str[
            TRACE_ID_DELIMITER_INDEX_1 + 1 : TRACE_ID_DELIMITER_INDEX_2
        ]
        unique_id_subset = trace_id_str[
            TRACE_ID_DELIMITER_INDEX_2 + 1 : TRACE_ID_LENGTH
        ]
        return int(timestamp_subset + unique_id_subset, 16)

    @staticmethod
    def _validate_span_id(span_id_str):
        return len(span_id_str) == PARENT_ID_LENGTH

    @staticmethod
    def _parse_span_id(span_id_str):
        return int(span_id_str, 16)

    @staticmethod
    def _validate_sampled_flag(sampled_flag_str):
        return len(sampled_flag_str) == SAMPLED_FLAG_LENGTH and sampled_flag_str in (
            IS_SAMPLED,
            NOT_SAMPLED,
        )

    @staticmethod
    def _parse_sampled_flag(sampled_flag_str):
        return sampled_flag_str[0] == IS_SAMPLED

    @staticmethod
    def _parse_lineage_header(xray_lineage_header):
        num_of_delimiters = xray_lineage_header.count(LINEAGE_DELIMITER)

        if (
            len(xray_lineage_header) < LINEAGE_MIN_LENGTH
            or len(xray_lineage_header) > LINEAGE_MAX_LENGTH
            or num_of_delimiters != 2
        ):
            return INVALID_LINEAGE_HEADER

        return xray_lineage_header

    @staticmethod
    def _is_valid_lineage(key):
        split = key.split(LINEAGE_DELIMITER)
        lineage_hash = split[1]
        counter1 = AwsXRayPropagator._parse_natural_or_return_negative(split[0], 10)
        counter2 = AwsXRayPropagator._parse_natural_or_return_negative(
            split[2], 10
        )

        is_hash_valid = (
            len(lineage_hash) == LINEAGE_HASH_LENGTH
            and AwsXRayPropagator._parse_natural_or_return_negative(lineage_hash, 16)
            != -1
        )
        is_valid_counter1 = (
            LINEAGE_MIN_COUNTER <= counter1 <= LINEAGE_MAX_COUNTER1
        )
        is_valid_counter2 = (
            LINEAGE_MIN_COUNTER
            <= counter2
            <= LINEAGE_MAX_COUNTER2
        )

        return is_hash_valid and is_valid_counter1 and is_valid_counter2

    @staticmethod
    def _parse_natural_or_return_negative(value, base):
        try:
            val = int(value, base)

            if val < 0:
                return -1
            return val
        except ValueError:
            return -1

    def inject(
        self,
        carrier: CarrierT,
        context: typing.Optional[Context] = None,
        setter: Setter[CarrierT] = default_setter,
    ) -> None:
        span = trace.get_current_span(context=context)

        span_context = span.get_span_context()
        if not span_context.is_valid:
            return

        otel_trace_id = f"{span_context.trace_id:032x}"
        xray_trace_id = TRACE_ID_DELIMITER.join(
            [
                TRACE_ID_VERSION,
                otel_trace_id[:TRACE_ID_FIRST_PART_LENGTH],
                otel_trace_id[TRACE_ID_FIRST_PART_LENGTH:],
            ]
        )

        parent_id = f"{span_context.span_id:016x}"

        sampling_flag = (
            IS_SAMPLED
            if span_context.trace_flags & trace.TraceFlags.SAMPLED
            else NOT_SAMPLED
        )

        # TODO: Add OT trace state to the X-Ray trace header

        trace_header = KV_PAIR_DELIMITER.join(
            [
                KEY_AND_VALUE_DELIMITER.join([key, value])
                for key, value in [
                    (TRACE_ID_KEY, xray_trace_id),
                    (PARENT_ID_KEY, parent_id),
                    (SAMPLED_FLAG_KEY, sampling_flag),
                ]
            ]
        )

        lineage = baggage.get_baggage(LINEAGE_KEY, context=context)

        if lineage is not None:
            trace_header += (
                f"{KV_PAIR_DELIMITER}{LINEAGE_KEY}{KEY_AND_VALUE_DELIMITER}{lineage}"
            )

        # 256 character truncation
        truncated_trace_header = trace_header[:256]

        setter.set(
            carrier,
            TRACE_HEADER_KEY,
            truncated_trace_header,
        )

    @property
    def fields(self):
        """Returns a set with the fields set in `inject`."""

        return {TRACE_HEADER_KEY}


class AwsXRayLambdaPropagator(AwsXRayPropagator):
    """Implementation of the AWS X-Ray Trace Header propagation protocol but
    with special handling for Lambda's ``_X_AMZN_TRACE_ID`` environment
    variable.
    """

    def extract(
        self,
        carrier: CarrierT,
        context: typing.Optional[Context] = None,
        getter: Getter[CarrierT] = default_getter,
    ) -> Context:
        xray_context = super().extract(carrier, context=context, getter=getter)

        if trace.get_current_span(context=context).get_span_context().is_valid:
            return xray_context

        trace_header = environ.get(AWS_TRACE_HEADER_ENV_KEY)

        if trace_header is None:
            return xray_context

        return super().extract(
            {TRACE_HEADER_KEY: trace_header},
            context=xray_context,
            getter=getter,
        )
