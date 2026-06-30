# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
Backward-compatibility helpers for the renamed log record attributes.

As of this release, ``opentelemetry-instrumentation-logging`` sets the
spec-compliant snake_case attribute names (``span_id``, ``trace_id``,
``trace_flags``, ``service_name``) on injected log records instead of the
legacy camelCase names (``otelSpanID``, ``otelTraceID``, ``otelTraceSampled``,
``otelServiceName``).

The legacy names are kept working via :class:`DeprecatedAttr`, a data
descriptor installed directly on ``logging.LogRecord`` (the stdlib class)
for the duration of instrumentation. It forwards reads of the legacy
attribute name to the new attribute name and emits a ``DeprecationWarning``
each time it is accessed. This avoids breaking existing user code (and
pre-built logging formats) that reference the old names, while steering
people toward the new, spec-compliant names.

The legacy aliases are scheduled for removal in a future release.
"""

# pylint: disable=no-member

import logging  # pylint: disable=import-self
import warnings

# Maps legacy attribute name -> new attribute name.
RENAMED_ATTRIBUTES = {
    "otelSpanID": "span_id",
    "otelTraceID": "trace_id",
    "otelTraceSampled": "trace_flags",
    "otelServiceName": "service_name",
}


class DeprecatedAttr:
    """Data descriptor that proxies a deprecated attribute to its replacement.

    Reads of the legacy name are forwarded to ``new_name`` on the same
    instance and emit a ``DeprecationWarning``. Writes to the legacy name
    are also forwarded, so any code that still assigns the old name directly
    (e.g. inside a custom ``log_hook``) stays in sync with the new name.

    Must be installed as a *class* attribute (see ``install``/``uninstall``
    below) -- assigning it as an instance attribute does nothing, since plain
    instance assignment doesn't go through the descriptor protocol.
    """

    def __init__(self, old_name: str, new_name: str):
        self.old_name = old_name
        self.new_name = new_name

    def __set_name__(self, owner, name):
        # Covers the case where this descriptor is assigned in a class body
        # (e.g. in tests) rather than via setattr() in install() below.
        if not self.old_name:
            self.old_name = name

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        warnings.warn(
            f"LogRecord attribute '{self.old_name}' is deprecated and will "
            f"be removed in a future release. Use '{self.new_name}' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return getattr(instance, self.new_name)

    def __set__(self, instance, value):
        setattr(instance, self.new_name, value)


_installed = False


def install():
    """Install deprecated-attribute proxies onto ``logging.LogRecord``.

    Idempotent: calling this more than once has no additional effect.
    """
    global _installed  # pylint: disable=global-statement
    if _installed:
        return
    for old_name, new_name in RENAMED_ATTRIBUTES.items():
        setattr(
            logging.LogRecord, old_name, DeprecatedAttr(old_name, new_name)
        )
    _installed = True


def uninstall():
    """Remove the deprecated-attribute proxies from ``logging.LogRecord``.

    Safe to call even if ``install`` was never called.
    """
    global _installed  # pylint: disable=global-statement
    for old_name in RENAMED_ATTRIBUTES:
        if old_name in logging.LogRecord.__dict__:
            delattr(logging.LogRecord, old_name)
    _installed = False
