# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import logging
from pathlib import Path

from opentelemetry.sdk.resources import Resource, ResourceDetector
from opentelemetry.semconv.resource import ResourceAttributes

_LOGGER = logging.getLogger(__name__)
_MACHINE_ID_PATHS = (
    Path("/etc/machine-id"),
    Path("/var/lib/dbus/machine-id"),
)


def _get_machine_id(paths=None):
    """Return the first non-empty machine id available on this host."""
    paths = _MACHINE_ID_PATHS if paths is None else paths
    for path in paths:
        try:
            machine_id = path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError) as exception:
            _LOGGER.debug("Could not read machine id from %s: %s", path, exception)
            continue
        if machine_id:
            return machine_id
    return None


class HostIdResourceDetector(ResourceDetector):
    """Detect the stable host identifier from the Linux machine-id files."""

    def detect(self) -> Resource:
        try:
            machine_id = _get_machine_id()
            if machine_id:
                return Resource({ResourceAttributes.HOST_ID: machine_id})
            return Resource.get_empty()
        except Exception as exception:  # pylint: disable=broad-except
            _LOGGER.warning(
                "%s resource detection failed: %s",
                self.__class__.__name__,
                exception,
            )
            if self.raise_on_error:
                raise
            return Resource.get_empty()
