# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from opentelemetry.instrumentation.http._internal._semconv import (
    HTTP_REQUEST_BODY_SIZE,
    HTTP_REQUEST_SIZE,
    HTTP_RESPONSE_BODY_SIZE,
    HTTP_RESPONSE_SIZE,
)
from opentelemetry.semconv.attributes.http_attributes import (
    HTTP_REQUEST_RESEND_COUNT,
    HTTP_RESPONSE_STATUS_CODE,
)


def get_status_code_attributes(status_code: int | None) -> dict[str, int]:
    """Return ``http.response.status_code``."""
    if status_code is None:
        return {}
    return {HTTP_RESPONSE_STATUS_CODE: status_code}


def get_resend_count_attributes(resend_count: int | None) -> dict[str, int]:
    """Return ``http.request.resend_count`` when the request was resent."""
    if resend_count is None or resend_count < 1:
        return {}
    return {HTTP_REQUEST_RESEND_COUNT: resend_count}


def _get_size_attributes(
    body_size: int | None,
    total_size: int | None,
    *,
    body_size_key: str,
    total_size_key: str,
    capture_body_size: bool,
    capture_size: bool,
) -> dict[str, int]:
    attributes: dict[str, int] = {}
    if capture_body_size and body_size is not None:
        attributes[body_size_key] = body_size
    if capture_size and total_size is not None:
        attributes[total_size_key] = total_size
    return attributes


def get_request_size_attributes(
    body_size: int | None, total_size: int | None, *, capture_body_size: bool, capture_size: bool
) -> dict[str, int]:
    """Return the enabled ``http.request.body.size`` and ``http.request.size`` attributes."""
    return _get_size_attributes(
        body_size,
        total_size,
        body_size_key=HTTP_REQUEST_BODY_SIZE,
        total_size_key=HTTP_REQUEST_SIZE,
        capture_body_size=capture_body_size,
        capture_size=capture_size,
    )


def get_response_size_attributes(
    body_size: int | None, total_size: int | None, *, capture_body_size: bool, capture_size: bool
) -> dict[str, int]:
    """Return the enabled ``http.response.body.size`` and ``http.response.size`` attributes."""
    return _get_size_attributes(
        body_size,
        total_size,
        body_size_key=HTTP_RESPONSE_BODY_SIZE,
        total_size_key=HTTP_RESPONSE_SIZE,
        capture_body_size=capture_body_size,
        capture_size=capture_size,
    )
