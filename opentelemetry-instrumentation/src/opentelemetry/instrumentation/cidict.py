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

from __future__ import annotations

from typing import (
    Any,
    Generic,
    Iterable,
    Iterator,
    Mapping,
    MutableMapping,
    Optional,
    Tuple,
    TypeVar,
    Union,
)

KT = TypeVar("KT")
VT = TypeVar("VT")


class CIDict(MutableMapping[KT, VT], Generic[KT, VT]):
    def __init__(
        self,
        data: Optional[Union[Mapping[KT, VT], Iterable[Tuple[KT, VT]]]] = None,
    ) -> None:
        self._data: dict[KT, Tuple[KT, VT]] = {}
        if data is None:
            data = {}
        self.update(data)

    @staticmethod
    def _normalize_key(key: KT) -> KT:
        if isinstance(key, str):
            return key.lower()  # type: ignore
        return key

    def _get_entry(self, key: KT) -> Tuple[KT, VT]:
        normalized_key = self._normalize_key(key)
        if normalized_key in self._data:
            return self._data[normalized_key]
        raise KeyError(repr(key))

    def original_key(self, key: KT) -> KT:
        return self._get_entry(key)[0]

    def normalized_items(self) -> Iterable[Tuple[KT, VT]]:
        return ((key, value[1]) for key, value in self._data.items())

    def __setitem__(self, key: KT, value: VT, /) -> None:
        self._data[self._normalize_key(key)] = (key, value)

    def __delitem__(self, key: KT, /) -> None:
        try:
            del self._data[self._normalize_key(key)]
        except KeyError:
            raise KeyError(repr(key)) from None

    def __getitem__(self, key: KT, /) -> VT:
        return self._get_entry(key)[1]

    def __len__(self) -> int:
        return len(self._data)

    def __iter__(self) -> Iterator[KT]:
        return (key for key, _ in self._data.values())

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({dict(self.items())!r})"

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, CIDict):
            return dict(self.normalized_items()) == dict(
                other.normalized_items()
            )
        if not isinstance(other, Mapping):
            return False
        ciother: CIDict[Any, Any] = CIDict(other)
        return dict(self.normalized_items()) == dict(
            ciother.normalized_items()
        )
