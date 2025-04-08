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

from pydantic import BaseModel
from opentelemetry.instrumentation.google_genai import dict_util


class PydanticModel(BaseModel):
    """Used to verify handling of pydantic models in the flattener."""

    str_value: str = ""
    int_value: int = 0


class ModelDumpableNotPydantic:
    """Used to verify general handling of 'model_dump'."""

    def __init__(self, dump_output):
        self._dump_output = dump_output

    def model_dump(self):
        return self._dump_output


class NotJsonSerializable:
    def __init__(self):
        pass


def test_flatten_empty_dict():
    input_dict = {}
    output_dict = dict_util.flatten_dict(input_dict)
    assert output_dict is not None
    assert isinstance(output_dict, dict)
    assert not output_dict


def test_flatten_simple_dict():
    input_dict = {
        "int_key": 1,
        "string_key": "somevalue",
        "float_key": 3.14,
        "bool_key": True,
    }
    assert dict_util.flatten_dict(input_dict) == input_dict


def test_flatten_nested_dict():
    input_dict = {
        "int_key": 1,
        "string_key": "somevalue",
        "float_key": 3.14,
        "bool_key": True,
        "object_key": {
            "nested": {
                "foo": 1,
                "bar": "baz",
            },
            "qux": 54321,
        },
    }
    assert dict_util.flatten_dict(input_dict) == {
        "int_key": 1,
        "string_key": "somevalue",
        "float_key": 3.14,
        "bool_key": True,
        "object_key.nested.foo": 1,
        "object_key.nested.bar": "baz",
        "object_key.qux": 54321,
    }


def test_flatten_with_key_exclusion():
    input_dict = {
        "int_key": 1,
        "string_key": "somevalue",
        "float_key": 3.14,
        "bool_key": True,
    }
    output = dict_util.flatten_dict(input_dict, exclude_keys=["int_key"])
    assert "int_key" not in output
    assert output == {
        "string_key": "somevalue",
        "float_key": 3.14,
        "bool_key": True,
    }


def test_flatten_with_renaming():
    input_dict = {
        "int_key": 1,
        "string_key": "somevalue",
        "float_key": 3.14,
        "bool_key": True,
    }
    output = dict_util.flatten_dict(
        input_dict, rename_keys={"float_key": "math_key"}
    )
    assert "float_key" not in output
    assert "math_key" in output
    assert output == {
        "int_key": 1,
        "string_key": "somevalue",
        "math_key": 3.14,
        "bool_key": True,
    }


def test_flatten_with_prefixing():
    input_dict = {
        "int_key": 1,
        "string_key": "somevalue",
        "float_key": 3.14,
        "bool_key": True,
    }
    output = dict_util.flatten_dict(input_dict, key_prefix="someprefix")
    assert output == {
        "someprefix.int_key": 1,
        "someprefix.string_key": "somevalue",
        "someprefix.float_key": 3.14,
        "someprefix.bool_key": True,
    }


def test_flatten_with_custom_flatten_func():
    def summarize_int_list(key, value, **kwargs):
        total = 0
        for item in value:
            total += item
        avg = total / len(value)
        return f"{len(value)} items (total: {total}, average: {avg})"

    flatten_functions = {"some.deeply.nested.key": summarize_int_list}
    input_dict = {
        "some": {
            "deeply": {
                "nested": {
                    "key": [1, 2, 3, 4, 5, 6, 7, 8, 9],
                },
            },
        },
        "other": [1, 2, 3, 4, 5, 6, 7, 8, 9],
    }
    output = dict_util.flatten_dict(
        input_dict, flatten_functions=flatten_functions
    )
    assert output == {
        "some.deeply.nested.key": "9 items (total: 45, average: 5.0)",
        "other": [1, 2, 3, 4, 5, 6, 7, 8, 9],
    }


def test_flatten_with_pydantic_model_value():
    input_dict = {
        "foo": PydanticModel(str_value="bar", int_value=123),
    }

    output = dict_util.flatten_dict(input_dict)
    assert output == {
        "foo.str_value": "bar",
        "foo.int_value": 123,
    }


def test_flatten_with_model_dumpable_value():
    input_dict = {
        "foo": ModelDumpableNotPydantic(
            {
                "str_value": "bar",
                "int_value": 123,
            }
        ),
    }

    output = dict_util.flatten_dict(input_dict)
    assert output == {
        "foo.str_value": "bar",
        "foo.int_value": 123,
    }


def test_flatten_with_mixed_structures():
    input_dict = {
        "foo": ModelDumpableNotPydantic(
            {
                "pydantic": PydanticModel(str_value="bar", int_value=123),
            }
        ),
    }

    output = dict_util.flatten_dict(input_dict)
    assert output == {
        "foo.pydantic.str_value": "bar",
        "foo.pydantic.int_value": 123,
    }


def test_flatten_with_complex_object_not_json_serializable():
    result = dict_util.flatten_dict(
            {
                "cannot_serialize_directly": NotJsonSerializable(),
            }
        )
    assert result is not None
    assert isinstance(result, dict)
    assert len(result) == 0


def test_flatten_good_with_non_serializable_complex_object():
    result = dict_util.flatten_dict(
            {
                "foo": {
                    "bar": "blah",
                    "baz": 5,
                },
                "cannot_serialize_directly": NotJsonSerializable(),
            }
        )
    assert result == {
        "foo.bar": "blah",
        "foo.baz": 5,
    }


def test_flatten_with_complex_object_not_json_serializable_and_custom_flatten_func():
    def flatten_not_json_serializable(key, value, **kwargs):
        assert isinstance(value, NotJsonSerializable)
        return "blah"

    output = dict_util.flatten_dict(
        {
            "cannot_serialize_directly": NotJsonSerializable(),
        },
        flatten_functions={
            "cannot_serialize_directly": flatten_not_json_serializable,
        },
    )
    assert output == {
        "cannot_serialize_directly": "blah",
    }


def test_flatten_simple_homogenous_primitive_string_list():
    input_dict = {"list_value": ["abc", "def"]}
    assert dict_util.flatten_dict(input_dict) == input_dict


def test_flatten_simple_homogenous_primitive_int_list():
    input_dict = {"list_value": [123, 456]}
    assert dict_util.flatten_dict(input_dict) == input_dict


def test_flatten_simple_homogenous_primitive_bool_list():
    input_dict = {"list_value": [True, False]}
    assert dict_util.flatten_dict(input_dict) == input_dict


def test_flatten_simple_heterogenous_primitive_list():
    input_dict = {"list_value": ["abc", 123]}
    assert dict_util.flatten_dict(input_dict) == {
        "list_value.length": 2,
        "list_value[0]": "abc",
        "list_value[1]": 123,
    }


def test_flatten_list_of_compound_types():
    input_dict = {
        "list_value": [
            {"a": 1, "b": 2},
            {"x": 100, "y": 123, "z": 321},
            "blah",
            [
                "abc",
                123,
            ],
        ]
    }
    assert dict_util.flatten_dict(input_dict) == {
        "list_value.length": 4,
        "list_value[0].a": 1,
        "list_value[0].b": 2,
        "list_value[1].x": 100,
        "list_value[1].y": 123,
        "list_value[1].z": 321,
        "list_value[2]": "blah",
        "list_value[3].length": 2,
        "list_value[3][0]": "abc",
        "list_value[3][1]": 123,
    }


def test_handles_simple_output_from_flatten_func():
    def f(*args, **kwargs):
        return "baz"

    input_dict = {
        "foo": PydanticModel(),
    }

    output = dict_util.flatten_dict(input_dict, flatten_functions={"foo": f})

    assert output == {
        "foo": "baz",
    }


def test_handles_compound_output_from_flatten_func():
    def f(*args, **kwargs):
        return {"baz": 123, "qux": 456}

    input_dict = {
        "foo": PydanticModel(),
    }

    output = dict_util.flatten_dict(input_dict, flatten_functions={"foo": f})

    assert output == {
        "foo.baz": 123,
        "foo.qux": 456,
    }
