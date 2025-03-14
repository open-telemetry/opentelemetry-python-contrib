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


from opentelemetry.instrumentation.google_genai import dict_util


def test_flatten_empty_dict():
    d = {}
    assert dict_util.flatten_dict(d) == d


def test_flatten_simple_dict():
    d = {
        "int_key": 1,
        "string_key": "somevalue",
        "float_key": 3.14,
        "bool_key": True
    }
    assert dict_util.flatten_dict(d) == d


def test_flatten_nested_dict():
    d = {
        "int_key": 1,
        "string_key": "somevalue",
        "float_key": 3.14,
        "bool_key": True,
        "object_key": {
            "nested": {
                "foo": 1,
                "bar": "baz",
            },
            "qux": 54321
        }
    }
    assert dict_util.flatten_dict(d) == {
        "int_key": 1,
        "string_key": "somevalue",
        "float_key": 3.14,
        "bool_key": True,
        "object_key.nested.foo": 1,
        "object_key.nested.bar": "baz",
        "object_key.qux": 54321,
    }


def test_flatten_with_key_exclusion():
    d = {
        "int_key": 1,
        "string_key": "somevalue",
        "float_key": 3.14,
        "bool_key": True
    }
    output = dict_util.flatten_dict(d, exclude_keys=["int_key"])
    assert "int_key" not in output
    assert output == {
        "string_key": "somevalue",
        "float_key": 3.14,
        "bool_key": True
    }


def test_flatten_with_renaming():
    d = {
        "int_key": 1,
        "string_key": "somevalue",
        "float_key": 3.14,
        "bool_key": True
    }
    output = dict_util.flatten_dict(
        d,
        rename_keys={"float_key": "math_key"})
    assert "float_key" not in output
    assert "math_key" in output
    assert output == {
        "int_key": 1,
        "string_key": "somevalue",
        "math_key": 3.14,
        "bool_key": True
    }


def test_flatten_with_prefixing():
    d = {
        "int_key": 1,
        "string_key": "somevalue",
        "float_key": 3.14,
        "bool_key": True
    }
    output = dict_util.flatten_dict(d, key_prefix="someprefix")
    assert output == {
        "someprefix.int_key": 1,
        "someprefix.string_key": "somevalue",
        "someprefix.float_key": 3.14,
        "someprefix.bool_key": True
    }


def test_flatten_with_custom_flatten_func():
    def summarize_int_list(key, value, **kwargs):
        total = 0
        for item in value:
            total += item
        avg = total / len(value)
        return f"{len(value)} items (total: {total}, average: {avg})"
    flatten_functions = {
         "some.deeply.nested.key": summarize_int_list
    }
    d = {
        "some": {
            "deeply": {
                "nested": {
                    "key": [1, 2, 3, 4, 5, 6, 7, 8, 9],
                },
            },
        },
        "other": [1, 2, 3, 4, 5, 6, 7, 8, 9]
    }
    output = dict_util.flatten_dict(d, flatten_functions=flatten_functions)
    assert output == {
        "some.deeply.nested.key": "9 items (total: 45, average: 5.0)",
        "other": [1, 2, 3, 4, 5, 6, 7, 8, 9],
    }
