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


import json
from typing import Any, Callable, Dict, Optional, Sequence, Set, Union

Primitive = Union[bool, str, int, float]
BoolList = list[bool]
StringList = list[str]
IntList = list[int]
FloatList = list[float]
HomogenousPrimitiveList = Union[BoolList, StringList, IntList, FloatList]
FlattenedValue = Union[Primitive, HomogenousPrimitiveList]
FlattenedDict = Dict[str, FlattenedValue]


def _concat_key(prefix: Optional[str], suffix: str):
    if not prefix:
        return suffix
    return f"{prefix}.{suffix}"


def _is_primitive(v):
    for t in [str, bool, int, float]:
        if isinstance(v, t):
            return True
    return False


def _is_homogenous_primitive_list(v):
    if not isinstance(v, list):
        return False
    if len(v) == 0:
        return True
    if not _is_primitive(v[0]):
        return False
    t = type(v[0])
    for entry in v[1:]:
        if not isinstance(entry, t):
            return False
    return True


def _get_flatten_func(
    flatten_functions: Dict[str, Callable], key_names: set[str]
):
    for key in key_names:
        flatten_func = flatten_functions.get(key)
        if flatten_func is not None:
            return flatten_func
    return None


def _flatten_value(
    key: str,
    value: Any,
    exclude_keys: Set[str],
    rename_keys: Dict[str, str],
    flatten_functions: Dict[str, Callable],
    _from_json=False,
) -> FlattenedDict:
    if value is None:
        return {}
    key_names = set([key])
    renamed_key = rename_keys.get(key)
    if renamed_key is not None:
        key_names.add(renamed_key)
        key = renamed_key
    if key_names & exclude_keys:
        return {}
    if _is_primitive(value):
        return {key: value}
    flatten_func = _get_flatten_func(flatten_functions, key_names)
    if flatten_func is not None:
        func_output = flatten_func(
            key,
            value,
            exclude_keys=exclude_keys,
            rename_keys=rename_keys,
            flatten_functions=flatten_functions,
        )
        if func_output is not None:
            return {key: func_output}
    if isinstance(value, dict):
        return _flatten_dict(
            value,
            key_prefix=key,
            exclude_keys=exclude_keys,
            rename_keys=rename_keys,
            flatten_functions=flatten_functions,
        )
    if isinstance(value, list):
        if _is_homogenous_primitive_list(value):
            return {key: value}
        return _flatten_list(
            value,
            key_prefix=key,
            exclude_keys=exclude_keys,
            rename_keys=rename_keys,
            flatten_functions=flatten_functions,
        )
    if hasattr(value, "model_dump"):
        d = value.model_dump()
        return _flatten_dict(
            d,
            key_prefix=key,
            exclude_keys=exclude_keys,
            rename_keys=rename_keys,
            flatten_functions=flatten_functions,
        )
    if _from_json:
        raise ValueError(
            f"Cannot flatten value with key {key}; value: {value}"
        )
    json_value = json.loads(json.dumps(value))
    return _flatten_value(
        key,
        json_value,
        exclude_keys=exclude_keys,
        rename_keys=rename_keys,
        flatten_functions=flatten_functions,
        _from_json=True,
    )


def _flatten_dict(
    d: Dict[str, Any],
    key_prefix: str,
    exclude_keys: Set[str],
    rename_keys: Dict[str, str],
    flatten_functions: Dict[str, Callable],
) -> FlattenedDict:
    result = {}
    for key, value in d.items():
        if key in exclude_keys:
            continue
        full_key = _concat_key(key_prefix, key)
        flattened = _flatten_value(
            full_key,
            value,
            exclude_keys=exclude_keys,
            rename_keys=rename_keys,
            flatten_functions=flatten_functions,
        )
        result.update(flattened)
    return result


def _flatten_list(
    lst: list[Any],
    key_prefix: str,
    exclude_keys: Set[str],
    rename_keys: Dict[str, str],
    flatten_functions: Dict[str, Callable],
) -> FlattenedDict:
    result = {}
    result[_concat_key(key_prefix, "length")] = len(lst)
    for index, value in enumerate(lst):
        full_key = f"{key_prefix}[{index}]"
        flattened = _flatten_value(
            full_key,
            value,
            exclude_keys=exclude_keys,
            rename_keys=rename_keys,
            flatten_functions=flatten_functions,
        )
        result.update(flattened)
    return result


def flatten_dict(
    d: Dict[str, Any],
    key_prefix: Optional[str] = None,
    exclude_keys: Optional[Sequence[str]] = None,
    rename_keys: Optional[Dict[str, str]] = None,
    flatten_functions: Optional[Dict[str, Callable]] = None,
):
    key_prefix = key_prefix or ""
    if exclude_keys is None:
        exclude_keys = set()
    elif isinstance(exclude_keys, list):
        exclude_keys = set(exclude_keys)
    rename_keys = rename_keys or {}
    flatten_functions = flatten_functions or {}
    return _flatten_dict(
        d,
        key_prefix=key_prefix,
        exclude_keys=exclude_keys,
        rename_keys=rename_keys,
        flatten_functions=flatten_functions,
    )
