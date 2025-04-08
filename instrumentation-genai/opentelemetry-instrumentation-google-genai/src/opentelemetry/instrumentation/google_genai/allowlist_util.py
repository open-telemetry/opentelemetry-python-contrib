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

import re
import os
from typing import Callable, Iterable, Optional, Set, Union

ALLOWED = True
DENIED = False


def _parse_env_list(s: str) -> Set[str]:
    result = set()
    for entry in s.split(","):
        stripped_entry = entry.strip()
        if not stripped_entry:
            continue
        result.add(stripped_entry)
    return result


class _CompoundMatcher:

    def __init__(self, entries: Set[str]):
        self._match_all = '*' in entries
        self._entries = entries
        self._regex_matcher = None
        regex_entries = []
        for entry in entries:
            if "*" not in entry:
                continue
            if entry == "*":
                continue
            entry = entry.replace("[", "\\[")
            entry = entry.replace("]", "\\]")
            entry = entry.replace(".", "\\.")
            entry = entry.replace("*", ".*")
            regex_entries.append(f"({entry})")
        if regex_entries:
            joined_regex = '|'.join(regex_entries)
            regex_str = f"^({joined_regex})$"
            self._regex_matcher = re.compile(regex_str)
    
    @property
    def match_all(self):
        return self._match_all

    def matches(self, x):
        if self._match_all:
            return True
        if x in self._entries:
            return True
        if (self._regex_matcher is not None) and (self._regex_matcher.fullmatch(x)):
            return True
        return False


class AllowList:
    def __init__(
        self,
        includes: Optional[Iterable[str]] = None,
        excludes: Optional[Iterable[str]] = None,
    ):
        self._includes = _CompoundMatcher(set(includes or []))
        self._excludes = _CompoundMatcher(set(excludes or []))
        assert ((not self._includes.match_all) or (not self._excludes.match_all)), "Can't have '*' in both includes and excludes."

    def allowed(self, x: str):
        if self._excludes.match_all:
            return self._includes.matches(x)
        if self._includes.match_all:
            return not self._excludes.matches(x)
        return self._includes.matches(x) and not self._excludes.matches(x)

    @staticmethod
    def from_env(
        includes_env_var: str, excludes_env_var: Optional[str] = None
    ):
        includes = _parse_env_list(os.getenv(includes_env_var) or "")
        excludes = set()
        if excludes_env_var:
            excludes = _parse_env_list(os.getenv(excludes_env_var) or "")
        return AllowList(includes=includes, excludes=excludes)
