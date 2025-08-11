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

import threading
from typing import Dict, Union, Optional, Any
import contextvars

# Context variable to store the current labeler
_labeler_context: contextvars.ContextVar[Optional["Labeler"]] = contextvars.ContextVar(
    "otel_labeler", default=None
)


class Labeler:
    """
    Labeler is used to allow instrumented web applications to add custom attributes
    to the metrics recorded by OpenTelemetry instrumentations.
    
    This class is thread-safe and can be used to accumulate custom attributes
    that will be included in OpenTelemetry metrics for the current request.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._attributes: Dict[str, Union[str, int, float, bool]] = {}

    def add(self, key: str, value: Union[str, int, float, bool]) -> None:
        """
        Add a single attribute to the labeler.
        
        Args:
            key: The attribute key
            value: The attribute value (must be a primitive type)
        """
        if not isinstance(value, (str, int, float, bool)):
            raise ValueError(f"Attribute value must be str, int, float, or bool, got {type(value)}")
        
        with self._lock:
            self._attributes[key] = value

    def add_attributes(self, attributes: Dict[str, Union[str, int, float, bool]]) -> None:
        """
        Add multiple attributes to the labeler.
        
        Args:
            attributes: Dictionary of attributes to add
        """
        for key, value in attributes.items():
            if not isinstance(value, (str, int, float, bool)):
                raise ValueError(f"Attribute value for '{key}' must be str, int, float, or bool, got {type(value)}")
        
        with self._lock:
            self._attributes.update(attributes)

    def get_attributes(self) -> Dict[str, Union[str, int, float, bool]]:
        """
        Returns a copy of all attributes added to the labeler.
        """
        with self._lock:
            return self._attributes.copy()

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


def get_labeler_attributes() -> Dict[str, Union[str, int, float, bool]]:
    """
    Get attributes from the current labeler, if any.
    
    Returns:
        Dictionary of custom attributes, or empty dict if no labeler exists
    """
    labeler = _labeler_context.get()
    if labeler is None:
        return {}
    return labeler.get_attributes()


def enhance_metric_attributes(
    base_attributes: Dict[str, Any], 
    include_custom: bool = True,
    max_custom_attrs: int = 20,
    max_attr_value_length: int = 100
) -> Dict[str, Any]:
    """
    Enhance metric attributes with custom labeler attributes.
    
    This function combines base metric attributes with custom attributes
    from the current labeler.
    
    Args:
        base_attributes: The base attributes for the metric
        include_custom: Whether to include custom labeler attributes
        max_custom_attrs: Maximum number of custom attributes to include
        max_attr_value_length: Maximum length for string attribute values
        
    Returns:
        Enhanced attributes dictionary combining base and custom attributes
    """
    if not include_custom:
        return base_attributes.copy()
    
    # Get custom attributes from labeler
    custom_attributes = get_labeler_attributes()
    if not custom_attributes:
        return base_attributes.copy()
    
    # Create enhanced attributes dict
    enhanced_attributes = base_attributes.copy()
    
    # Filter and add custom attributes with safety checks
    added_count = 0
    for key, value in custom_attributes.items():
        if added_count >= max_custom_attrs:
            break
            
        # Skip attributes that would override base attributes
        if key in base_attributes:
            continue
            
        # Apply value length limit for strings
        if isinstance(value, str) and len(value) > max_attr_value_length:
            value = value[:max_attr_value_length]
        
        # Only include safe attribute types
        if isinstance(value, (str, int, float, bool)):
            enhanced_attributes[key] = value
            added_count += 1
    
    return enhanced_attributes
