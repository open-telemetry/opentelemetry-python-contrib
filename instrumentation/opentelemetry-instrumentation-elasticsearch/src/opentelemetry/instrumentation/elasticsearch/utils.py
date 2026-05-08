# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
import json

sanitized_value = "?"


def _mask_leaf_nodes(obj):
    """
    Recursively traverses JSON structure and masks leaf node values.
    Leaf nodes are final values that are no longer dict or list.
    """
    if isinstance(obj, dict):
        return {key: _mask_leaf_nodes(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [_mask_leaf_nodes(item) for item in obj]
    # Mask leaf node
    return sanitized_value


def sanitize_body(body) -> str:
    if isinstance(body, str):
        body = json.loads(body)

    masked_body = _mask_leaf_nodes(body)
    return str(masked_body)
