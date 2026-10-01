# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from collections.abc import Iterable
from logging import getLogger
from re import compile as re_compile
from typing import Any

from opentelemetry.baggage import get_all, set_baggage
from opentelemetry.context import Context
from opentelemetry.propagators.textmap import (
    CarrierT,
    Getter,
    Setter,
    TextMapPropagator,
    default_getter,
    default_setter,
)
from opentelemetry.trace import (
    INVALID_SPAN_ID,
    INVALID_TRACE_ID,
    NonRecordingSpan,
    SpanContext,
    TraceFlags,
    get_current_span,
    set_span_in_context,
)

_logger = getLogger(__name__)

OT_TRACE_ID_HEADER = "ot-tracer-traceid"
OT_SPAN_ID_HEADER = "ot-tracer-spanid"
OT_SAMPLED_HEADER = "ot-tracer-sampled"
OT_BAGGAGE_PREFIX = "ot-baggage-"

# https://www.w3.org/TR/baggage/#limits
_MAX_BAGGAGE_ENTRIES = 180
_MAX_BAGGAGE_BYTES_PER_ENTRY = 4096
_MAX_BAGGAGE_TOTAL_BYTES = 8192

_valid_header_name = re_compile(r"[\w_^`!#$%&'*+.|~]+")
_valid_header_value = re_compile(r"[\t\x20-\x7e\x80-\xff]+")
_valid_extract_traceid = re_compile(r"[0-9a-f]{1,32}")
_valid_extract_spanid = re_compile(r"[0-9a-f]{1,16}")


class OTTracePropagator(TextMapPropagator):
    """Propagator for the OTTrace HTTP header format"""

    def extract(
        self,
        carrier: CarrierT,
        context: Context | None = None,
        getter: Getter[CarrierT] = default_getter,
    ) -> Context:
        if context is None:
            context = Context()

        traceid = _extract_identifier(
            getter.get(carrier, OT_TRACE_ID_HEADER),
            _valid_extract_traceid,
            INVALID_TRACE_ID,
        )

        spanid = _extract_identifier(
            getter.get(carrier, OT_SPAN_ID_HEADER),
            _valid_extract_spanid,
            INVALID_SPAN_ID,
        )

        if _extract_first_element(getter.get(carrier, OT_SAMPLED_HEADER)) == "true":
            traceflags = TraceFlags.SAMPLED
        else:
            traceflags = TraceFlags.DEFAULT

        if traceid != INVALID_TRACE_ID and spanid != INVALID_SPAN_ID:
            context = set_span_in_context(
                NonRecordingSpan(
                    SpanContext(
                        trace_id=traceid,
                        span_id=spanid,
                        is_remote=True,
                        trace_flags=TraceFlags(traceflags),
                    )
                ),
                context,
            )

            baggage = dict(get_all(context)) or {}

            # Use len() as a fast byte approximation to avoid encoding overhead.
            total_bytes = sum(len(k) + len(v) for k, v in baggage.items())
            num_baggage_entries = len(baggage)
            for key in getter.keys(carrier):
                if not key.startswith(OT_BAGGAGE_PREFIX):
                    continue

                value = _extract_first_element(getter.get(carrier, key))
                if value is None:
                    continue

                # Count every ot-baggage-* entry towards the cap *before*
                # the per-entry byte check, so a flood of oversized entries
                # cannot keep the loop running past the cap.
                if num_baggage_entries >= _MAX_BAGGAGE_ENTRIES:
                    _logger.warning("ot-baggage exceeded the maximum number of list-members")
                    break
                num_baggage_entries += 1

                baggage_key = key[len(OT_BAGGAGE_PREFIX) :]
                entry_bytes = len(baggage_key) + len(value)
                if entry_bytes > _MAX_BAGGAGE_BYTES_PER_ENTRY:
                    _logger.warning(
                        "ot-baggage entry with key `%s` exceeded the maximum number of bytes per list-member",
                        baggage_key,
                    )
                    continue

                delta_bytes = entry_bytes - (
                    len(baggage_key) + len(baggage[baggage_key]) if baggage_key in baggage else 0
                )
                if total_bytes + delta_bytes > _MAX_BAGGAGE_TOTAL_BYTES:
                    _logger.warning("ot-baggage exceeded the maximum number of total bytes")
                    break

                total_bytes += delta_bytes
                baggage[baggage_key] = value

            for key, value in baggage.items():
                context = set_baggage(key, value, context)

        return context

    def inject(
        self,
        carrier: CarrierT,
        context: Context | None = None,
        setter: Setter[CarrierT] = default_setter,
    ) -> None:
        span_context = get_current_span(context).get_span_context()

        if span_context.trace_id == INVALID_TRACE_ID:
            return

        setter.set(carrier, OT_TRACE_ID_HEADER, hex(span_context.trace_id)[2:][-16:])
        setter.set(
            carrier,
            OT_SPAN_ID_HEADER,
            hex(span_context.span_id)[2:][-16:],
        )

        if span_context.trace_flags == TraceFlags.SAMPLED:
            traceflags = "true"
        else:
            traceflags = "false"

        setter.set(carrier, OT_SAMPLED_HEADER, traceflags)

        baggage = get_all(context)

        if not baggage:
            return

        total_bytes = 0
        num_baggage_entries = 0
        for header_name, header_value in baggage.items():
            if num_baggage_entries >= _MAX_BAGGAGE_ENTRIES:
                _logger.warning("ot-baggage exceeded the maximum number of list-members")
                break
            num_baggage_entries += 1

            entry_bytes = len(header_name) + len(header_value)
            if entry_bytes > _MAX_BAGGAGE_BYTES_PER_ENTRY:
                _logger.warning(
                    "ot-baggage entry with key `%s` exceeded the maximum number of bytes per list-member",
                    header_name,
                )
                continue

            if _valid_header_name.fullmatch(header_name) is None or _valid_header_value.fullmatch(header_value) is None:
                continue

            if total_bytes + entry_bytes > _MAX_BAGGAGE_TOTAL_BYTES:
                _logger.warning("ot-baggage exceeded the maximum number of total bytes")
                break

            total_bytes += entry_bytes
            setter.set(
                carrier,
                "".join([OT_BAGGAGE_PREFIX, header_name]),
                header_value,
            )

    @property
    def fields(self):
        """Returns a set with the fields set in `inject`.

        See
        `opentelemetry.propagators.textmap.TextMapPropagator.fields`
        """
        return {
            OT_TRACE_ID_HEADER,
            OT_SPAN_ID_HEADER,
            OT_SAMPLED_HEADER,
        }


def _extract_first_element(
    items: Iterable[CarrierT],
    default: Any = None,
) -> CarrierT | None:
    if items is None:
        return default
    return next(iter(items), None)


def _extract_identifier(items: Iterable[CarrierT], validator_pattern, default: int) -> int:
    header = _extract_first_element(items)
    if header is None or validator_pattern.fullmatch(header) is None:
        return default

    try:
        return int(header, 16)
    except ValueError:
        return default
