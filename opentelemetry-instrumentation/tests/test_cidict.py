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

# pylint: disable=redefined-outer-name

from typing import Any, Optional

import pytest

from opentelemetry.instrumentation.cidict import CIDict


@pytest.fixture
def simple_cidict() -> CIDict[str, int]:
    return CIDict({"Alpha": 1, "Beta": 2, "Gamma": 3})


@pytest.mark.parametrize(
    "data, expected_len",
    [
        (None, 0),
        ({}, 0),
        ({"a": 1, "b": 2}, 2),
        ({"A": 1, "a": 2}, 1),
    ],
)
def test_init_from_mapping(
    data: Optional[dict[str, int]], expected_len: int
) -> None:
    assert len(CIDict(data)) == expected_len


@pytest.mark.parametrize(
    "pairs, expected_len",
    [
        ([], 0),
        ([("x", 10), ("y", 20)], 2),
        ([("X", 1), ("x", 2)], 1),
    ],
)
def test_init_from_iterable_of_pairs(
    pairs: list[tuple[str, int]], expected_len: int
) -> None:
    assert len(CIDict(pairs)) == expected_len


def test_init_non_string_keys() -> None:
    cid: CIDict[int, str] = CIDict({1: "one", 2: "two"})
    assert cid[1] == "one"
    assert cid[2] == "two"


@pytest.mark.parametrize("key", ["Alpha", "alpha", "ALPHA", "aLpHa"])
def test_getitem_case_insensitive(
    simple_cidict: CIDict[str, int], key: str
) -> None:
    assert simple_cidict[key] == 1


def test_getitem_missing_raises(simple_cidict: CIDict[str, int]) -> None:
    with pytest.raises(KeyError):
        _ = simple_cidict["missing"]


@pytest.mark.parametrize(
    "set_key, get_key, value",
    [
        ("Hello", "hello", 99),
        ("WORLD", "world", 42),
        ("MiXeD", "mixed", 7),
    ],
)
def test_setitem_case_insensitive(
    set_key: str, get_key: str, value: int
) -> None:
    cid: CIDict[str, int] = CIDict()
    cid[set_key] = value
    assert cid[get_key] == value


def test_setitem_overwrite_updates_original_key() -> None:
    cid: CIDict[str, int] = CIDict()
    cid["Hello"] = 1
    cid["HELLO"] = 2
    assert cid["hello"] == 2
    assert cid.original_key("hello") == "HELLO"


@pytest.mark.parametrize("del_key", ["Alpha", "alpha", "ALPHA", "aLpHa"])
def test_delitem_case_insensitive(
    simple_cidict: CIDict[str, int], del_key: str
) -> None:
    del simple_cidict[del_key]
    assert "alpha" not in simple_cidict
    assert len(simple_cidict) == 2


def test_delitem_missing_raises(simple_cidict: CIDict[str, int]) -> None:
    with pytest.raises(KeyError):
        del simple_cidict["nonexistent"]


def test_iter_yields_original_keys(simple_cidict: CIDict[str, int]) -> None:
    assert set(simple_cidict) == {"Alpha", "Beta", "Gamma"}


@pytest.mark.parametrize(
    "lookup_key, expected_original",
    [
        ("Alpha", "Alpha"),
        ("alpha", "Alpha"),
        ("ALPHA", "Alpha"),
    ],
)
def test_original_key(
    simple_cidict, lookup_key: str, expected_original: str
) -> None:
    assert simple_cidict.original_key(lookup_key) == expected_original


def test_normalized_items(simple_cidict: CIDict[str, int]) -> None:
    items = list(simple_cidict.normalized_items())
    assert set(items) == {("alpha", 1), ("beta", 2), ("gamma", 3)}


@pytest.mark.parametrize(
    "key, expected",
    [
        ("Alpha", True),
        ("alpha", True),
        ("ALPHA", True),
        ("missing", False),
    ],
)
def test_contains(
    simple_cidict: CIDict[str, int], key: str, expected: bool
) -> None:
    assert (key in simple_cidict) is expected


@pytest.mark.parametrize(
    "other, expected",
    [
        (CIDict({"alpha": 1, "beta": 2, "gamma": 3}), True),
        (CIDict({"ALPHA": 1, "BETA": 2, "GAMMA": 3}), True),
        ({"alpha": 1, "beta": 2, "gamma": 3}, True),
        ({"ALPHA": 1, "BETA": 2, "GAMMA": 3}, True),
        (CIDict({"alpha": 99, "beta": 2, "gamma": 3}), False),
        (CIDict({"alpha": 1, "beta": 2}), False),
        ("not a mapping", False),
        (42, False),
    ],
)
def test_eq(
    simple_cidict: CIDict[str, int], other: Any, expected: bool
) -> None:
    assert (simple_cidict == other) is expected


def test_repr(simple_cidict: CIDict[str, int]) -> None:
    assert repr(simple_cidict) == "CIDict({'Alpha': 1, 'Beta': 2, 'Gamma': 3})"


@pytest.mark.parametrize(
    "pop_key, expected_value, remaining_len",
    [
        ("Alpha", 1, 2),
        ("BETA", 2, 2),
        ("gamma", 3, 2),
    ],
)
def test_pop(
    simple_cidict: CIDict[str, int],
    pop_key: str,
    expected_value: int,
    remaining_len: int,
) -> None:
    assert simple_cidict.pop(pop_key) == expected_value
    assert len(simple_cidict) == remaining_len


def test_setdefault_existing(simple_cidict: CIDict[str, int]) -> None:
    assert simple_cidict.setdefault("ALPHA", 999) == 1
    assert simple_cidict["alpha"] == 1


def test_setdefault_missing(simple_cidict: CIDict[str, int]) -> None:
    assert simple_cidict.setdefault("Delta", 4) == 4
    assert simple_cidict["delta"] == 4


def test_keys(simple_cidict: CIDict[str, int]) -> None:
    assert set(simple_cidict.keys()) == {"Alpha", "Beta", "Gamma"}


def test_values(simple_cidict: CIDict[str, int]) -> None:
    assert set(simple_cidict.values()) == {1, 2, 3}


def test_items(simple_cidict: CIDict[str, int]) -> None:
    assert set(simple_cidict.items()) == {
        ("Alpha", 1),
        ("Beta", 2),
        ("Gamma", 3),
    }
