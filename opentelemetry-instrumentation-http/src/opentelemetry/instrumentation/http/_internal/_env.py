# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
import re
from os import environ

_logger = logging.getLogger(__name__)


def _get_env_var(name: str) -> str | None:
    value = environ.get(name)
    if value is None or not value.strip():
        return None
    return value.strip()


def parse_bool_env_var(name: str) -> bool | None:
    value = _get_env_var(name)
    if value is None:
        return None
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    _logger.warning("Ignoring invalid value %r for %s: expected 'true' or 'false'", value, name)
    return None


def parse_int_env_var(name: str) -> int | None:
    value = _get_env_var(name)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        _logger.warning("Ignoring invalid value %r for %s: expected an integer", value, name)
        return None


def parse_list_env_var(name: str) -> tuple[str, ...] | None:
    value = _get_env_var(name)
    if value is None:
        return None
    entries = tuple(entry.strip() for entry in value.split(",") if entry.strip())
    return entries or None


def parse_patterns_env_var(name: str, flags: int = 0) -> tuple[re.Pattern[str], ...] | None:
    entries = parse_list_env_var(name)
    if entries is None:
        return None
    try:
        return tuple(re.compile(entry, flags) for entry in entries)
    except re.error as exc:
        _logger.warning("Ignoring invalid value for %s: %s", name, exc)
        return None
