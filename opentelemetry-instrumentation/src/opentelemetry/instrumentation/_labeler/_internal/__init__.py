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

import contextvars
import logging
import threading
from types import MappingProxyType
from typing import Any, Dict, Mapping, Optional, Union

from opentelemetry.util.types import AttributeValue

# Context variable to store the current labeler
_labeler_context: contextvars.ContextVar[Optional["Labeler"]] = (
    contextvars.ContextVar("otel_labeler", default=None)
)

_logger = logging.getLogger(__name__)


class Labeler:
    """
    Stores custom attributes for the current request in context.

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
        self._attributes: Dict[str, Union[str, int, float, bool]] = {}
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
                    break

                if (
                    isinstance(value, str)
                    and len(value) > self._max_attr_value_length
                ):
                    value = value[: self._max_attr_value_length]

                self._attributes[key] = value

    def get_attributes(self) -> Mapping[str, Union[str, int, float, bool]]:
        """
        Returns a copy of all attributes added to the labeler.
        """
        with self._lock:
            return MappingProxyType(self._attributes)

    def clear(self) -> None:
        with self._lock:
            self._attributes.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._attributes)


def get_labeler() -> Labeler:
    """
    Get the Labeler instance for the current request context.

    If no Labeler exists in the current context, a new one is created
    and stored in the context.

    Returns:
        Labeler instance for the current request, or a new empty Labeler
        if not in a request context
    """
    labeler = _labeler_context.get()
    if labeler is None:
        labeler = Labeler()
        _labeler_context.set(labeler)
    return labeler


def set_labeler(labeler: Labeler) -> None:
    """
    Set the Labeler instance for the current request context.

    Args:
        labeler: The Labeler instance to set
    """
    _labeler_context.set(labeler)


def clear_labeler() -> None:
    """
    Clear the Labeler instance from the current request context.
    """
    _labeler_context.set(None)


def get_labeler_attributes() -> Mapping[str, Union[str, int, float, bool]]:
    """
    Get attributes from the current labeler, if any.

    Returns:
        Dictionary of custom attributes, or empty dict if no labeler exists
    """
    labeler = _labeler_context.get()
    if labeler is None:
        empty_attributes: Dict[str, Union[str, int, float, bool]] = {}
        return MappingProxyType(empty_attributes)
    return labeler.get_attributes()


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

    labeler = _labeler_context.get()
    if labeler is None:
        return base_attributes.copy()

    custom_attributes = labeler.get_attributes()
    if not custom_attributes:
        return base_attributes.copy()

    enriched_attributes = base_attributes.copy()

    added_count = 0
    for key, value in custom_attributes.items():
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
