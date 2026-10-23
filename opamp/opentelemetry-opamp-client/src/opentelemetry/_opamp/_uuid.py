# Copyright (c) 2001-2025 Python Software Foundation; All Rights Reserved.
# SPDX-License-Identifier: PSF-2.0

"""UUIDv7 backport from CPython 3.14's Lib/uuid.py.

Adapted to use explicit byte order and the public UUID constructor for
Python 3.10 compatibility. Only the UUIDv7 implementation is included.
See LICENSE.PSF for the Python Software Foundation license.
"""

from __future__ import annotations

import os
import time
from uuid import UUID

_RFC_4122_VERSION_7_FLAGS = (7 << 76) | (0x8000 << 48)

_last_timestamp_v7: int | None = None
_last_counter_v7: int = 0  # 42-bit counter


def _uuid7_get_counter_and_tail() -> tuple[int, int]:
    rand = int.from_bytes(os.urandom(10), "big")
    # 42-bit counter with MSB set to 0
    counter = (rand >> 32) & 0x1FF_FFFF_FFFF
    # 32-bit random data
    tail = rand & 0xFFFF_FFFF
    return counter, tail


def uuid7() -> UUID:
    """Generate a UUID from a Unix timestamp in milliseconds and random bits.

    UUIDv7 objects feature monotonicity within a millisecond.
    """
    # --- 48 ---   -- 4 --   --- 12 ---   -- 2 --   --- 30 ---   - 32 -
    # unix_ts_ms | version | counter_hi | variant | counter_lo | random
    #
    # 'counter = counter_hi | counter_lo' is a 42-bit counter constructed
    # with Method 1 of RFC 9562, §6.2, and its MSB is set to 0.
    #
    # 'random' is a 32-bit random value regenerated for every new UUID.
    #
    # If multiple UUIDs are generated within the same millisecond, the LSB
    # of 'counter' is incremented by 1. When overflowing, the timestamp is
    # advanced and the counter is reset to a random 42-bit integer with MSB
    # set to 0.

    # pylint: disable=global-statement
    global _last_timestamp_v7
    global _last_counter_v7

    nanoseconds = time.time_ns()
    timestamp_ms = nanoseconds // 1_000_000

    if _last_timestamp_v7 is None or timestamp_ms > _last_timestamp_v7:
        counter, tail = _uuid7_get_counter_and_tail()
    else:
        if timestamp_ms < _last_timestamp_v7:
            timestamp_ms = _last_timestamp_v7 + 1
        # advance the 42-bit counter
        counter = _last_counter_v7 + 1
        if counter > 0x3FF_FFFF_FFFF:
            # advance the 48-bit timestamp
            timestamp_ms += 1
            counter, tail = _uuid7_get_counter_and_tail()
        else:
            # 32-bit random data
            tail = int.from_bytes(os.urandom(4), "big")

    unix_ts_ms = timestamp_ms & 0xFFFF_FFFF_FFFF
    counter_msbs = counter >> 30
    # keep 12 counter's MSBs and clear variant bits
    counter_hi = counter_msbs & 0x0FFF
    # keep 30 counter's LSBs and clear version bits
    counter_lo = counter & 0x3FFF_FFFF
    # ensure that the tail is always a 32-bit integer (by construction,
    # it is already the case, but future interfaces may allow the user
    # to specify the random tail)
    tail &= 0xFFFF_FFFF

    int_uuid_7 = unix_ts_ms << 80
    int_uuid_7 |= counter_hi << 64
    int_uuid_7 |= counter_lo << 32
    int_uuid_7 |= tail
    # by construction, the variant and version bits are already cleared
    int_uuid_7 |= _RFC_4122_VERSION_7_FLAGS
    res = UUID(int=int_uuid_7)

    # defer global update until all computations are done
    _last_timestamp_v7 = timestamp_ms
    _last_counter_v7 = counter
    return res
