# Copyright (c) 2001-2025 Python Software Foundation; All Rights Reserved.
# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0 AND PSF-2.0

"""UUIDv7 tests adapted from CPython's Lib/test/test_uuid.py."""

from __future__ import annotations

from itertools import pairwise
from random import Random
from unittest import mock
from uuid import RFC_4122, UUID

import pytest

from opentelemetry._opamp import _uuid


@pytest.fixture(autouse=True)
def reset_uuid7_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_uuid, "_last_timestamp_v7", None)
    monkeypatch.setattr(_uuid, "_last_counter_v7", 0)


def _assert_uuid7_fields(value: UUID, timestamp_ms: int, counter: int, tail: int) -> None:
    assert value.variant == RFC_4122
    assert value.version == 7
    assert value.int >> 80 == timestamp_ms & 0xFFFF_FFFF_FFFF
    assert (value.int >> 64) & 0xFFF == counter >> 30
    assert (value.int >> 32) & 0x3FFF_FFFF == counter & 0x3FFF_FFFF
    assert value.int & 0xFFFF_FFFF == tail
    assert _uuid._last_timestamp_v7 == timestamp_ms
    assert _uuid._last_counter_v7 == counter


def test_uuid7_layout(monkeypatch: pytest.MonkeyPatch) -> None:
    timestamp_ms = 0x0123456789AB
    monkeypatch.setattr(_uuid.time, "time_ns", lambda: timestamp_ms * 1_000_000)
    monkeypatch.setattr(_uuid.os, "urandom", lambda size: b"\xff" * size)

    value = _uuid.uuid7()

    assert isinstance(value, UUID)
    assert len(value.bytes) == 16
    assert value.version == 7
    assert value.variant == RFC_4122
    assert value.int >> 80 == timestamp_ms
    # Random initialization clears the high bit of the 42-bit counter.
    assert value.hex == "0123456789ab77ffbfffffffffffffff"


def test_uuid7_random_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    timestamp_ns = 1672533296_123_456_789
    timestamp_ms = timestamp_ns // 1_000_000
    monkeypatch.setattr(_uuid.time, "time_ns", lambda: timestamp_ns)
    random = Random(0)

    for _ in range(100):
        counter = (random.getrandbits(11) << 30) | random.getrandbits(30)
        tail = random.getrandbits(32)
        # Set the seven unused high bits to ensure they are discarded.
        random_bits = (((1 << 7) - 1) << 73) | (counter << 32) | tail
        monkeypatch.setattr(_uuid, "_last_timestamp_v7", None)
        monkeypatch.setattr(_uuid, "_last_counter_v7", 0)

        with mock.patch.object(_uuid.os, "urandom", return_value=random_bits.to_bytes(10, "big")) as urandom:
            value = _uuid.uuid7()

        urandom.assert_called_once_with(10)
        _assert_uuid7_fields(value, timestamp_ms, counter, tail)
        assert (value.int >> 75) & 1 == 0


def test_uuid7_uniqueness() -> None:
    values = {_uuid.uuid7() for _ in range(1000)}

    assert len(values) == 1000
    assert {value.version for value in values} == {7}


def test_uuid7_monotonicity() -> None:
    values = [_uuid.uuid7() for _ in range(10_000)]

    assert values == sorted(values)


def test_uuid7_counter_increment_and_fresh_tail(monkeypatch: pytest.MonkeyPatch) -> None:
    timestamp_ns = 1672533296_123_456_789
    next_timestamp_ns = 1672533296_123_457_032
    timestamp_ms = timestamp_ns // 1_000_000
    assert next_timestamp_ns // 1_000_000 == timestamp_ms
    timestamps = iter([timestamp_ns, next_timestamp_ns])
    monkeypatch.setattr(_uuid.time, "time_ns", lambda: next(timestamps))
    monkeypatch.setattr(_uuid, "_last_timestamp_v7", 0)
    counter = (0x345 << 30) | 0x12345678
    tail = 0x12345678
    next_tail = 0xABCDEF01
    random_bits = (counter << 32) | tail

    with mock.patch.object(_uuid.os, "urandom", return_value=random_bits.to_bytes(10, "big")) as urandom:
        first = _uuid.uuid7()

    urandom.assert_called_once_with(10)
    _assert_uuid7_fields(first, timestamp_ms, counter, tail)

    with mock.patch.object(_uuid.os, "urandom", return_value=next_tail.to_bytes(4, "big")) as urandom:
        second = _uuid.uuid7()

    urandom.assert_called_once_with(4)
    _assert_uuid7_fields(second, timestamp_ms, counter + 1, next_tail)
    assert first < second


def test_uuid7_monotonic_within_millisecond(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_uuid.time, "time_ns", lambda: 1_000_000_000)
    monkeypatch.setattr(_uuid.os, "urandom", bytes)

    values = [_uuid.uuid7() for _ in range(100)]

    assert all(value.int >> 80 == 1000 for value in values)
    assert all(left.int < right.int for left, right in pairwise(values))


def test_uuid7_new_millisecond_resets_counter(monkeypatch: pytest.MonkeyPatch) -> None:
    timestamps = iter([1_000_000_000, 1_001_000_000])
    monkeypatch.setattr(_uuid.time, "time_ns", lambda: next(timestamps))
    random_values = iter([b"\xff" * 10, bytes(10)])
    monkeypatch.setattr(_uuid.os, "urandom", lambda size: next(random_values))

    first = _uuid.uuid7()
    second = _uuid.uuid7()

    assert first.int < second.int
    assert second.int >> 80 == 1001
    assert second.hex == "0000000003e970008000000000000000"


def test_uuid7_clock_rollback(monkeypatch: pytest.MonkeyPatch) -> None:
    timestamp_ns = 1672533296_123_456_789
    timestamp_ms = timestamp_ns // 1_000_000
    last_timestamp_ms = timestamp_ms + 1
    counter = (0x345 << 30) | 0x12345678
    tail = 0xABCDEF01
    monkeypatch.setattr(_uuid, "_last_timestamp_v7", last_timestamp_ms)
    monkeypatch.setattr(_uuid, "_last_counter_v7", counter)
    monkeypatch.setattr(_uuid.time, "time_ns", lambda: timestamp_ns)

    with mock.patch.object(_uuid.os, "urandom", return_value=tail.to_bytes(4, "big")) as urandom:
        value = _uuid.uuid7()

    urandom.assert_called_once_with(4)
    _assert_uuid7_fields(value, last_timestamp_ms + 1, counter + 1, tail)


def test_uuid7_overflow_reseeds_counter(monkeypatch: pytest.MonkeyPatch) -> None:
    timestamp_ns = 1672533296_123_456_789
    timestamp_ms = timestamp_ns // 1_000_000
    new_counter = (0x345 << 30) | 0x12345678
    tail = 0xABCDEF01
    random_bits = (new_counter << 32) | tail
    monkeypatch.setattr(_uuid, "_last_timestamp_v7", timestamp_ms)
    monkeypatch.setattr(_uuid, "_last_counter_v7", (1 << 42) - 1)
    monkeypatch.setattr(_uuid.time, "time_ns", lambda: timestamp_ns)

    with mock.patch.object(_uuid.os, "urandom", return_value=random_bits.to_bytes(10, "big")) as urandom:
        value = _uuid.uuid7()

    urandom.assert_called_once_with(10)
    _assert_uuid7_fields(value, timestamp_ms + 1, new_counter, tail)


@pytest.mark.parametrize("counter", [(1 << 30) - 1, (1 << 42) - 1])
def test_uuid7_counter_carry(monkeypatch: pytest.MonkeyPatch, counter: int) -> None:
    monkeypatch.setattr(_uuid, "_last_timestamp_v7", 1000)
    monkeypatch.setattr(_uuid, "_last_counter_v7", counter)
    monkeypatch.setattr(_uuid.time, "time_ns", lambda: 1_000_000_000)
    monkeypatch.setattr(_uuid.os, "urandom", bytes)

    value = _uuid.uuid7()

    assert value.version == 7
    assert value.variant == RFC_4122
    if counter == (1 << 42) - 1:
        assert value.int >> 80 == 1001
        assert _uuid._last_counter_v7 == 0
    else:
        assert value.int >> 80 == 1000
        assert (value.int >> 64) & 0xFFF == 1
        assert (value.int >> 32) & 0x3FFFFFFF == 0
