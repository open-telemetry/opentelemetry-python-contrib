# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import logging
import threading
from types import MappingProxyType
from typing import Any, Dict, Mapping, Optional, Union

from opentelemetry.context import attach, create_key, get_value, set_value
from opentelemetry.util.types import AttributeValue

LABELER_CONTEXT_KEY = create_key("otel_labeler")

_logger = logging.getLogger(__name__)


class Labeler:
    """
    Stores custom attributes for the current OTel context.

    This feature is experimental and unstable.
    """

    def __init__(
        self, max_custom_attrs: int = 20, max_attr_value_length: int = 100
    ):
        """
        Initialize a new Labeler instance.

        Args:
            max_custom_attrs: Maximum number of custom attributes to store.
                When this limit is reached, new attributes will be ignored;
                existing attributes can still be updated.
            max_attr_value_length: Maximum length for string attribute values.
                String values exceeding this length will be truncated.
        """
        self._lock = threading.Lock()
        self._attributes: dict[str, Union[str, int, float, bool]] = {}
        self._max_custom_attrs = max_custom_attrs
        self._max_attr_value_length = max_attr_value_length

    def add(self, key: str, value: Any) -> None:
        """
        Add a single attribute to the labeler, subject to the labeler's limits:
        - If max_custom_attrs limit is reached and this is a new key, the attribute is ignored
        - String values exceeding max_attr_value_length are truncated

        Args:
            key: attribute key
            value: attribute value, must be a primitive type: str, int, float, or bool
        """
        if not isinstance(value, (str, int, float, bool)):
            _logger.warning(
                "Skipping attribute '%s': value must be str, int, float, or bool, got %s",
                key,
                type(value).__name__,
            )
            return

        with self._lock:
            if (
                len(self._attributes) >= self._max_custom_attrs
                and key not in self._attributes
            ):
                return

            if (
                isinstance(value, str)
                and len(value) > self._max_attr_value_length
            ):
                value = value[: self._max_attr_value_length]

            self._attributes[key] = value

    def add_attributes(self, attributes: Dict[str, Any]) -> None:
        """
        Add multiple attributes to the labeler, subject to the labeler's limits:
        - If max_custom_attrs limit is reached and this is a new key, the attribute is ignored
        - Existing attributes can still be updated
        - String values exceeding max_attr_value_length are truncated

        Args:
            attributes: Dictionary of attributes to add. Values must be primitive types
                (str, int, float, or bool)
        """
        with self._lock:
            for key, value in attributes.items():
                if not isinstance(value, (str, int, float, bool)):
                    _logger.warning(
                        "Skipping attribute '%s': value must be str, int, float, or bool, got %s",
                        key,
                        type(value).__name__,
                    )
                    continue

                if (
                    len(self._attributes) >= self._max_custom_attrs
                    and key not in self._attributes
                ):
                    continue

                if (
                    isinstance(value, str)
                    and len(value) > self._max_attr_value_length
                ):
                    value = value[: self._max_attr_value_length]

                self._attributes[key] = value

    def get_attributes(self) -> Mapping[str, Union[str, int, float, bool]]:
        """
        Return a read-only mapping view of attributes in this labeler.
        """
        with self._lock:
            return MappingProxyType(self._attributes)

    def clear(self) -> None:
        with self._lock:
            self._attributes.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._attributes)


def _attach_context_value(value: Optional[Labeler]) -> None:
    """
    Attach a new OpenTelemetry context containing the given labeler value.

    This helper is fail-safe: context attach errors are suppressed and
    logged at debug level.

    Args:
        value: Labeler instance to store in context, or ``None`` to clear it.
    """
    try:
        updated_context = set_value(LABELER_CONTEXT_KEY, value)
        attach(updated_context)
    except Exception:  # pylint: disable=broad-exception-caught
        _logger.debug("Failed to attach labeler context", exc_info=True)


def get_labeler() -> Labeler:
    """
    Get the Labeler instance for the current OTel context.

    If no Labeler exists in the current context, a new one is created
    and stored in the context.

    Returns:
        Labeler instance for the current OTel context, or a new empty Labeler
        if no Labeler is currently stored in context.
    """
    try:
        current_value = get_value(LABELER_CONTEXT_KEY)
    except Exception:  # pylint: disable=broad-exception-caught
        _logger.debug("Failed to read labeler from context", exc_info=True)
        current_value = None

    if isinstance(current_value, Labeler):
        return current_value

    labeler = Labeler()
    _attach_context_value(labeler)
    return labeler


def set_labeler(labeler: Any) -> None:
    """
    Set the Labeler instance for the current OTel context.

    Args:
        labeler: The Labeler instance to set
    """
    if not isinstance(labeler, Labeler):
        _logger.warning(
            "Skipping set_labeler: value must be Labeler, got %s",
            type(labeler).__name__,
        )
        return
    _attach_context_value(labeler)


def clear_labeler() -> None:
    """
    Clear the Labeler instance from the current OTel context.

    This is primarily intended for test isolation or manual context-lifecycle
    management. In typical framework-instrumented request handling,
    applications generally should not need to call this directly.
    """
    _attach_context_value(None)


def get_labeler_attributes() -> Mapping[str, Union[str, int, float, bool]]:
    """
    Get attributes from the current labeler, if any.

    Returns:
        Read-only mapping of custom attributes, or an empty read-only mapping
        if no labeler exists.
    """
    empty_attributes: Dict[str, Union[str, int, float, bool]] = {}
    try:
        current_value = get_value(LABELER_CONTEXT_KEY)
    except Exception:  # pylint: disable=broad-exception-caught
        _logger.debug(
            "Failed to read labeler attributes from context", exc_info=True
        )
        return MappingProxyType(empty_attributes)

    if not isinstance(current_value, Labeler):
        return MappingProxyType(empty_attributes)
    return current_value.get_attributes()


def enrich_metric_attributes(
    base_attributes: Dict[str, Any],
    enrich_enabled: bool = True,
) -> Dict[str, AttributeValue]:
    """
    Combines base_attributes with custom attributes from the current labeler,
    returning a new dictionary of attributes according to the labeler configuration:
    - Attributes that would override base_attributes are skipped
    - If max_custom_attrs limit is reached and this is a new key, the attribute is ignored
    - String values exceeding max_attr_value_length are truncated

    Args:
        base_attributes: The base attributes for the metric
        enrich_enabled: Whether to include custom labeler attributes

    Returns:
        Dictionary combining base and custom attributes. If no custom attributes,
        returns a copy of the original base attributes.
    """
    if not enrich_enabled:
        return base_attributes.copy()

    labeler_attributes = get_labeler_attributes()
    if not labeler_attributes:
        return base_attributes.copy()

    try:
        labeler = get_value(LABELER_CONTEXT_KEY)
    except Exception:  # pylint: disable=broad-exception-caught
        labeler = None

    if not isinstance(labeler, Labeler):
        return base_attributes.copy()

    enriched_attributes = base_attributes.copy()
    added_count = 0
    for key, value in labeler_attributes.items():
        if added_count >= labeler._max_custom_attrs:
            break
        if key in base_attributes:
            continue

        if (
            isinstance(value, str)
            and len(value) > labeler._max_attr_value_length
        ):
            value = value[: labeler._max_attr_value_length]

        enriched_attributes[key] = value
        added_count += 1

    return enriched_attributes
