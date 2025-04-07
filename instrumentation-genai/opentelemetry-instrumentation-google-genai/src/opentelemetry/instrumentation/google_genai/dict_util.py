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
from typing import Any, Callable, Dict, Optional, Sequence, Set, Union, Tuple

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
    first_entry_value_type = type(v[0])
    for entry in v[1:]:
        if not isinstance(entry, first_entry_value_type):
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


def _flatten_with_flatten_func(
    key: str,
    value: Any,
    exclude_keys: Set[str],
    rename_keys: Dict[str, str],
    flatten_functions: Dict[str, Callable],
    key_names: Set[str]) -> Tuple[bool, Any]:
    flatten_func = _get_flatten_func(flatten_functions, key_names)
    if flatten_func is None:
        return False, value
    func_output = flatten_func(
            key,
            value,
            exclude_keys=exclude_keys,
            rename_keys=rename_keys,
            flatten_functions=flatten_functions,
        )
    if func_output is None:
        return True, {}
    if _is_primitive(func_output) or _is_homogenous_primitive_list(
        func_output):
        return True, {key: func_output}
    return False, func_output


def _flatten_compound_value(
    key: str,
    value: Any,
    exclude_keys: Set[str],
    rename_keys: Dict[str, str],
    flatten_functions: Dict[str, Callable],
    key_names: Set[str],
    _from_json=False,
) -> FlattenedDict:
    fully_flattened_with_flatten_func, value = _flatten_with_flatten_func(
        key=key,
        value=value,
        exclude_keys=exclude_keys,
        rename_keys=rename_keys,
        flatten_functions=flatten_functions,
        key_names=key_names)
    if fully_flattened_with_flatten_func:
        return value
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
        return _flatten_dict(
            value.model_dump(),
            key_prefix=key,
            exclude_keys=exclude_keys,
            rename_keys=rename_keys,
            flatten_functions=flatten_functions,
        )
    if _from_json:
        raise ValueError(
            f"Cannot flatten value with key {key}; value: {value}"
        )
    try:
        json_string = json.dumps(value)
    except TypeError as exc:
        raise ValueError(
            f"Cannot flatten value with key {key}; value: {value}. Not JSON serializable."
        ) from exc
    json_value = json.loads(json_string)
    return _flatten_value(
        key,
        json_value,
        exclude_keys=exclude_keys,
        rename_keys=rename_keys,
        flatten_functions=flatten_functions,
        # Ensure that we don't recurse indefinitely if "json.loads()" somehow returns
        # a complex, compound object that does not get handled by the "primitive", "list",
        # or "dict" cases. Prevents falling back on the JSON serialization fallback path.
        _from_json=True,
    )


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
    return _flatten_compound_value(
        key=key,
        value=value,
        exclude_keys=exclude_keys,
        rename_keys=rename_keys,
        flatten_functions=flatten_functions,
        key_names=key_names,
        _from_json=_from_json,
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
