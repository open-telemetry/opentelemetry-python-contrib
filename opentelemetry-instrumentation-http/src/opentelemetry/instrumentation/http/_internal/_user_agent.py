# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from typing import Literal

from opentelemetry.instrumentation.http._internal._headers import get_header_value
from opentelemetry.instrumentation.http._internal._semconv import (
    USER_AGENT_SYNTHETIC_TYPE,
)
from opentelemetry.semconv.attributes.user_agent_attributes import USER_AGENT_ORIGINAL

_logger = logging.getLogger(__name__)

_USER_AGENT_HEADER = "user-agent"

SyntheticTypeDetector = Callable[[str], Literal["bot", "test"] | None]


def get_user_agent(user_agent: str | None, headers: Mapping[str, str | Sequence[str]] | None) -> str | None:
    """Return ``user_agent``, or else the first ``User-Agent`` header value."""
    if user_agent:
        return user_agent
    return get_header_value(headers, _USER_AGENT_HEADER)


def get_user_agent_original_attributes(user_agent: str | None) -> dict[str, str]:
    """Return ``user_agent.original``."""
    if not user_agent:
        return {}
    return {USER_AGENT_ORIGINAL: user_agent}


def _detect_synthetic_type(detector: SyntheticTypeDetector, user_agent: str) -> str | None:
    try:
        return detector(user_agent)
    # pylint: disable-next=broad-exception-caught
    except Exception:
        _logger.warning("User agent synthetic type detector raised an exception", exc_info=True)
        return None


def get_synthetic_type_attributes(user_agent: str | None, detector: SyntheticTypeDetector | None) -> dict[str, str]:
    """Return ``user_agent.synthetic.type`` as classified by ``detector``."""
    if detector is None or not user_agent:
        return {}
    synthetic_type = _detect_synthetic_type(detector, user_agent)
    if not synthetic_type:
        return {}
    return {USER_AGENT_SYNTHETIC_TYPE: synthetic_type}
