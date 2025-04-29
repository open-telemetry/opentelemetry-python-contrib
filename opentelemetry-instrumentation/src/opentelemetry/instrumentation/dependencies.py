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

from logging import getLogger
from typing import Collection

from packaging.requirements import InvalidRequirement, Requirement

from opentelemetry.util._importlib_metadata import (
    PackageNotFoundError,
    version,
)

logger = getLogger(__name__)


class DependencyConflict:
    required: str | None = None
    found: str | None = None

    def __init__(self, required: str | None, found: str | None = None):
        self.required = required
        self.found = found

    def __str__(self):
        return f'DependencyConflict: requested: "{self.required}" but found: "{self.found}"'


class DependencyConflictError(Exception):
    conflict: DependencyConflict

    def __init__(self, conflict: DependencyConflict):
        self.conflict = conflict

    def __str__(self):
        return str(self.conflict)


def get_dependency_conflicts(
    deps: Collection[str | Requirement],
) -> DependencyConflict | None:
    for dep in deps:
        if isinstance(dep, Requirement):
            req = dep
        else:
            try:
                req = Requirement(dep)
            except InvalidRequirement as exc:
                logger.warning(
                    'error parsing dependency, reporting as a conflict: "%s" - %s',
                    dep,
                    exc,
                )
                return DependencyConflict(dep)

        try:
            dist_version = version(req.name)
        except PackageNotFoundError:
            return DependencyConflict(dep)

        if not req.specifier.contains(dist_version):
            return DependencyConflict(dep, f"{req.name} {dist_version}")
    return None
