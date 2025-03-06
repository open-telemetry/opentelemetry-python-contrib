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
