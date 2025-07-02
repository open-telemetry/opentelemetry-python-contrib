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

# TODO: consider replacing _either with _any or _or


class DependencyConflict:
    required: str | None = None
    found: str | None = None
    # The following fields are used when an instrumentation requires any of a set of dependencies rather than all.
    required_either: Collection[str] = []
    found_either: Collection[str] = []

    # TODO: No longer requires required field
    def __init__(
        self,
        required: str | None = None,
        found: str | None = None,
        required_either: Collection[str] = [],
        found_either: Collection[str] = [],
    ):
        self.required = required
        self.found = found
        # The following fields are used when an instrumentation requires any of a set of dependencies rather than all.
        self.required_either = required_either
        self.found_either = found_either

    def __str__(self):
        if not self.required and (self.required_either or self.found_either):
            print("EITHER STRING")
            # TODO: make sure this formats correctly
            return f'DependencyConflict: requested any of the following: "{self.required_either}" but found: "{self.found_either}"'
        print("AND STRING")
        return f'DependencyConflict: requested: "{self.required}" but found: "{self.found}"'


# TODO: Figure out if this should be a subclass of DependencyConflict.
# If now, change functions to return either and then ensure that all the dependents can handle the new value
# class DependencyConflictEither(DependencyConflict):
#     required: Collection[str] = []
#     found: Collection[str] = []

#     def __init__(self, required: Collection[str], found: Collection[str] = []):
#         self.required = required
#         self.found = found

#     def __str__(self):
#         return f'DependencyConflictEither: requested: "{self.required}" but found: "{self.found}"'


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
    # print(f"dist: {dist}")
    # print(f"dist.requires: {dist.requires}")
    if dist.requires:
        for dep in dist.requires:
            print(f"dep: {dep}")
            if extra not in dep:
                print(f"Skipping dep: {dep}")
                continue
            if instruments not in dep and instruments_either not in dep:
                print(f"Skipping dep: {dep}")
                continue

            req = Requirement(dep)
            # print(f"req: {req}")
            if req.marker.evaluate(instruments_marker):  # type: ignore
                # print("Evaluated. Append")
                instrumentation_deps.append(req)  # type: ignore
            if req.marker.evaluate(instruments_either_marker):  # type: ignore
                # print("Evaluated. either. Append")
                # Need someway to separate
                instrumentation_either_deps.append(req)  # type: ignore
    dc = get_dependency_conflicts(
        instrumentation_deps, instrumentation_either_deps
    )  # type: ignore
    print(f"dep conf: {dc}")
    return dc
    # return get_dependency_conflicts(instrumentation_deps, instrumentation_either_deps) # type: ignore


def get_dependency_conflicts(
    deps: Collection[
        str | Requirement
    ],  # Dependenciesall of which are required
    deps_either: Collection[
        str | Requirement
    ] = [],  # Dependencies any of which are required
) -> DependencyConflict | None:
    for dep in deps:
        # TODO: what is this?
        if isinstance(dep, Requirement):
            print("REQUIREMENT")
            req = dep
        else:
            try:
                print("NOT REQUIREMENT")
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
            # TODO: Technically this field should allow Requirements type. Tackle this in a separate PR.
            return DependencyConflict(dep)

        if not req.specifier.contains(dist_version):
            # TODO: Technically this field should allow Requirements type
            return DependencyConflict(dep, f"{req.name} {dist_version}")

    # TODO: add eval of deps_either
    if deps_either:
        # TODO: change to using DependencyConflict
        is_dependency_conflict = True
        required_either: Collection[str] = []
        found_either: Collection[str] = []
        for dep in deps_either:
            # TODO: what is this?
            if isinstance(dep, Requirement):
                print("REQUIREMENT")
                req = dep
            else:
                try:
                    print("NOT REQUIREMENT")
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
                # print(f"PackageNotFoundError EITHER: {req.name}")
                # TODO: anything here?
                # return DependencyConflict(dep)
                required_either.append(str(dep))
                continue

            if req.specifier.contains(dist_version):
                is_dependency_conflict = False
                # Since only one of the instrumentation_either dependencies is required, there is no dependency conflict.
                break
            else:
                required_either.append(str(dep))
                found_either.append(f"{req.name} {dist_version}")

        if is_dependency_conflict:
            # return DependencyConflict(dep, f"{req.name} {dist_version}")
            # print (f"required_either: {required_either}")
            # print (f"found_either: {found_either}")
            return DependencyConflict(
                required_either=required_either,
                found_either=found_either,
            )
        return None

    return None
