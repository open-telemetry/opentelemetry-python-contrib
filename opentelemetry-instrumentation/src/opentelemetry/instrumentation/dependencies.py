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
    Distribution,
    PackageNotFoundError,
    version,
)

logger = getLogger(__name__)


class DependencyConflict:
    required: str | None = None
    found: str | None = None
    # The following fields are used when an instrumentation requires any of a set of dependencies rather than all.
    required_either: Collection[str] = []
    found_either: Collection[str] = []

    def __init__(
        self,
        required: str | None = None,
        found: str | None = None,
        required_either: Collection[str] = None,
        found_either: Collection[str] = None,
    ):
        self.required = required
        self.found = found
        # The following fields are used when an instrumentation requires any of a set of dependencies rather than all.
        self.required_either = required_either
        self.found_either = found_either

    def __str__(self):
        if not self.required and (self.required_either or self.found_either):
            return f'DependencyConflict: requested any of the following: "{self.required_either}" but found: "{self.found_either}"'
        return f'DependencyConflict: requested: "{self.required}" but found: "{self.found}"'


class DependencyConflictError(Exception):
    conflict: DependencyConflict

    def __init__(self, conflict: DependencyConflict):
        self.conflict = conflict

    def __str__(self):
        return str(self.conflict)


def get_dist_dependency_conflicts(
    dist: Distribution,
) -> DependencyConflict | None:
    instrumentation_deps = []
    instrumentation_either_deps = []
    extra = "extra"
    instruments = "instruments"
    instruments_marker = {extra: instruments}
    instruments_either = "instruments_either"
    instruments_either_marker = {extra: instruments_either}
    if dist.requires:
        for dep in dist.requires:
            if extra not in dep:
                continue
            if instruments not in dep and instruments_either not in dep:
                continue

            req = Requirement(dep)
            if req.marker.evaluate(instruments_marker):  # type: ignore
                instrumentation_deps.append(req)  # type: ignore
            if req.marker.evaluate(instruments_either_marker):  # type: ignore
                instrumentation_either_deps.append(req)  # type: ignore
    return get_dependency_conflicts(
        instrumentation_deps, instrumentation_either_deps
    )  # type: ignore


def get_dependency_conflicts(
    deps: Collection[
        str | Requirement
    ],  # Dependencies all of which are required
    deps_either: Collection[
        str | Requirement
    ] = None,  # Dependencies any of which are required
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

    # If all the dependencies in "instruments" are present, check "instruments_either" for conflicts.
    if deps_either:
        return _get_dependency_conflicts_either(deps_either)
    return None


# This is a helper functions designed to ease reading and meet linting requirements.
def _get_dependency_conflicts_either(
    deps_either: Collection[str | Requirement],
) -> DependencyConflict | None:
    if not deps_either:
        return None
    is_dependency_conflict = True
    required_either: Collection[str] = []
    found_either: Collection[str] = []
    for dep in deps_either:
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
            required_either.append(str(dep))
            continue

        if req.specifier.contains(dist_version):
            # Since only one of the instrumentation_either dependencies is required, there is no dependency conflict.
            is_dependency_conflict = False
            break
        # If the version does not match, add it to the list of unfulfilled requirement options.
        required_either.append(str(dep))
        found_either.append(f"{req.name} {dist_version}")

    if is_dependency_conflict:
        return DependencyConflict(
            required_either=required_either,
            found_either=found_either,
        )
    return None
