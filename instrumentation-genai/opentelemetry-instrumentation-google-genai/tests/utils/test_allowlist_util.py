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

import os
from unittest import mock

from opentelemetry.instrumentation.google_genai.allowlist_util import AllowList


def test_empty_allowlist_allows_nothing():
    allow_list = AllowList()
    assert not allow_list.allowed("")
    assert not allow_list.allowed("foo")
    assert not allow_list.allowed("bar")
    assert not allow_list.allowed("baz")
    assert not allow_list.allowed("anything at all")


def test_simple_include_allow_list():
    allow_list = AllowList(includes=["abc", "xyz"])
    assert allow_list.allowed("abc")
    assert allow_list.allowed("xyz")
    assert not allow_list.allowed("blah")
    assert not allow_list.allowed("other value not in includes")


def test_includes_and_exclues():
    allow_list = AllowList(includes=["abc", "xyz"], excludes=["xyz"])
    assert allow_list.allowed("abc")
    assert not allow_list.allowed("xyz")
    assert not allow_list.allowed("blah")
    assert not allow_list.allowed("other value not in includes")


def test_default_include_with_excludes():
    allow_list = AllowList(includes=["*"], excludes=["foo", "bar"])
    assert not allow_list.allowed("foo")
    assert not allow_list.allowed("bar")
    assert allow_list.allowed("abc")
    assert allow_list.allowed("xyz")
    assert allow_list.allowed("blah")
    assert allow_list.allowed("other value not in includes")


def test_default_exclude_with_includes():
    allow_list = AllowList(includes=["foo", "bar"], excludes=["*"])
    assert allow_list.allowed("foo")
    assert allow_list.allowed("bar")
    assert not allow_list.allowed("abc")
    assert not allow_list.allowed("xyz")
    assert not allow_list.allowed("blah")
    assert not allow_list.allowed("other value not in includes")


@mock.patch.dict(os.environ, {"TEST_ALLOW_LIST_INCLUDE_KEYS": "abc,xyz"})
def test_can_load_from_env_with_just_include_list():
    allow_list = AllowList.from_env("TEST_ALLOW_LIST_INCLUDE_KEYS")
    assert allow_list.allowed("abc")
    assert allow_list.allowed("xyz")
    assert not allow_list.allowed("blah")
    assert not allow_list.allowed("other value not in includes")


@mock.patch.dict(
    os.environ, {"TEST_ALLOW_LIST_INCLUDE_KEYS": " abc , , xyz ,"}
)
def test_can_handle_spaces_and_empty_entries():
    allow_list = AllowList.from_env("TEST_ALLOW_LIST_INCLUDE_KEYS")
    assert allow_list.allowed("abc")
    assert allow_list.allowed("xyz")
    assert not allow_list.allowed("")
    assert not allow_list.allowed(",")
    assert not allow_list.allowed("blah")
    assert not allow_list.allowed("other value not in includes")


@mock.patch.dict(
    os.environ,
    {
        "TEST_ALLOW_LIST_INCLUDE_KEYS": "abc,xyz",
        "TEST_ALLOW_LIST_EXCLUDE_KEYS": "xyz, foo, bar",
    },
)
def test_can_load_from_env_with_includes_and_excludes():
    allow_list = AllowList.from_env(
        "TEST_ALLOW_LIST_INCLUDE_KEYS",
        excludes_env_var="TEST_ALLOW_LIST_EXCLUDE_KEYS",
    )
    assert allow_list.allowed("abc")
    assert not allow_list.allowed("xyz")
    assert not allow_list.allowed("foo")
    assert not allow_list.allowed("bar")
    assert not allow_list.allowed("not in the list")


@mock.patch.dict(
    os.environ,
    {
        "TEST_ALLOW_LIST_INCLUDE_KEYS": "*",
        "TEST_ALLOW_LIST_EXCLUDE_KEYS": "xyz, foo, bar",
    },
)
def test_supports_wildcards_in_loading_from_env():
    allow_list = AllowList.from_env(
        "TEST_ALLOW_LIST_INCLUDE_KEYS",
        excludes_env_var="TEST_ALLOW_LIST_EXCLUDE_KEYS",
    )
    assert allow_list.allowed("abc")
    assert not allow_list.allowed("xyz")
    assert not allow_list.allowed("foo")
    assert not allow_list.allowed("bar")
    assert allow_list.allowed("blah")
    assert allow_list.allowed("not in the list")
