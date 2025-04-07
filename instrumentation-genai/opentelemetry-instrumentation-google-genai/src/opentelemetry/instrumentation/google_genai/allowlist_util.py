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
from typing import Optional, Set, Callable, List, Union

ALLOWED = True
DENIED = False

def _parse_env_list(s: str) -> Set[str]:
    result = set()
    for entry in s.split(','):
        stripped_entry = entry.strip()
        if not stripped_entry:
            continue
        result.add(stripped_entry)
    return result


class AllowList:

    def __init__(
        self,
        includes: Optional[Union[Set[str], List[str]]] = None,
        excludes: Optional[Union[Set[str], List[str]]] = None,
        if_none_match: Optional[Callable[str, bool]] = None):
        self._includes = set(includes or [])
        self._excludes = set(excludes or [])
        self._include_all = '*' in self._includes
        self._exclude_all = '*' in self._excludes
        assert (not self._include_all) or (not self._exclude_all), "Can't have '*' in both includes and excludes."

    def allowed(self, x: str):
        if self._exclude_all:
            return x in self._includes
        if self._include_all:
            return x not in self._excludes
        return (x in self._includes) and (x not in self._excludes)

    @staticmethod
    def from_env(
        includes_env_var: str,
        excludes_env_var: Optional[str] = None):
      includes = _parse_env_list(os.getenv(includes_env_var) or '')
      excludes = set()
      if excludes_env_var:
        excludes = _parse_env_list(os.getenv(excludes_env_var) or '')
      return AllowList(
        includes=includes,
        excludes=excludes)
