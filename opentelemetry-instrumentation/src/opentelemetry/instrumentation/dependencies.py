# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from collections.abc import Collection
from logging import Logger, getLogger

from packaging.requirements import InvalidRequirement, Requirement

from opentelemetry.util._importlib_metadata import (
    Distribution,
    PackageNotFoundError,
    version,
)

_logger = getLogger(__name__)


def _format_deps(deps: Collection[str]) -> str:
    return ", ".join(str(dep) for dep in deps)


class DependencyConflict:
    """Represents a dependency conflict in OpenTelemetry instrumentation.

    This class is used to track conflicts between required dependencies and the
    actual installed packages. It supports two scenarios:

    1. Standard conflicts where all dependencies are required
    2. Either/or conflicts where only one of a set of dependencies is required

    Attributes:
        required: The required dependency specification that conflicts with what's installed.
        found: The actual dependency that was found installed (if any).
        required_any: Collection of dependency specifications where any one would satisfy
            the requirement (for either/or scenarios).
        found_any: Collection of actual dependencies found for either/or scenarios.
    """

    required: str | None = None
    found: str | None = None
    # The following fields are used when an instrumentation requires any of a set of dependencies rather than all.
    required_any: Collection[str] = None
    found_any: Collection[str] = None

    def __init__(
        self,
        required: str | None = None,
        found: str | None = None,
        required_any: Collection[str] = None,
        found_any: Collection[str] = None,
    ):
        self.required = required
        self.found = found
        # The following fields are used when an instrumentation requires any of a set of dependencies rather than all.
        self.required_any = required_any
        self.found_any = found_any

    @property
    def _is_version_conflict(self) -> bool:
        """False when the dependency is not installed at all, rather than installed at an incompatible version."""
        return bool(self.found or self.found_any)

    def _log(self, logger: Logger, instrumentor_name: str) -> None:
        """Log as an error for a version conflict, at debug level when the dependency is not installed."""
        log = logger.error if self._is_version_conflict else logger.debug
        log(self._format_message(instrumentor_name))

    def _format_message(self, instrumentor_name: str | None = None) -> str:
        subject = instrumentor_name or "This instrumentation"
        if self.required:
            if self.found:
                return (
                    f'{subject} only instruments "{self.required}", '
                    f'but currently installed version ("{self.found}") falls outside of that range, '
                    f"so nothing can be instrumented."
                )
            return (
                f'{subject} only instruments "{self.required}", '
                f"but no installed version was found, so nothing can be instrumented."
            )
        if self.required_any:
            if self.found_any:
                return (
                    f'{subject} instruments any of "{_format_deps(self.required_any)}", '
                    f'but currently installed version(s) ("{_format_deps(self.found_any)}") fall outside of that range, '
                    f"so nothing can be instrumented."
                )
            return (
                f'{subject} requires any of "{_format_deps(self.required_any)}", '
                f"but none are installed, so nothing can be instrumented."
            )
        return f"{subject} has an unknown dependency conflict, so nothing can be instrumented."

    def __str__(self):
        return self._format_message()


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
    instrumentation_any_deps = []
    extra = "extra"
    instruments = "instruments"
    instruments_marker = {extra: instruments}
    instruments_any = "instruments-any"
    instruments_any_marker = {extra: instruments_any}
    if dist.requires:
        for dep in dist.requires:
            if extra not in dep:
                continue
            if instruments not in dep and instruments_any not in dep:
                continue

            req = Requirement(dep)
            if req.marker.evaluate(instruments_marker):  # type: ignore
                instrumentation_deps.append(req)  # type: ignore
            if req.marker.evaluate(instruments_any_marker):  # type: ignore
                instrumentation_any_deps.append(req)  # type: ignore
    return get_dependency_conflicts(instrumentation_deps, instrumentation_any_deps)  # type: ignore


def get_dependency_conflicts(
    deps: Collection[str | Requirement],  # Dependencies all of which are required
    deps_any: Collection[str | Requirement] | None = None,  # Dependencies any of which are required
) -> DependencyConflict | None:
    for dep in deps:
        if isinstance(dep, Requirement):
            req = dep
        else:
            try:
                req = Requirement(dep)
            except InvalidRequirement as exc:
                _logger.warning(
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

    # If all the dependencies in "instruments" are present, check "instruments-any" for conflicts.
    if deps_any:
        return _get_dependency_conflicts_any(deps_any)
    return None


# This is a helper functions designed to ease reading and meet linting requirements.
def _get_dependency_conflicts_any(
    deps_any: Collection[str | Requirement],
) -> DependencyConflict | None:
    if not deps_any:
        return None
    is_dependency_conflict = True
    required_any: Collection[str] = []
    found_any: Collection[str] = []
    for dep in deps_any:
        if isinstance(dep, Requirement):
            req = dep
        else:
            try:
                req = Requirement(dep)
            except InvalidRequirement as exc:
                _logger.warning(
                    'error parsing dependency, reporting as a conflict: "%s" - %s',
                    dep,
                    exc,
                )
                return DependencyConflict(dep)

        try:
            dist_version = version(req.name)
        except PackageNotFoundError:
            required_any.append(str(dep))
            continue

        if req.specifier.contains(dist_version):
            # Since only one of the instrumentation_any dependencies is required, there is no dependency conflict.
            is_dependency_conflict = False
            break
        # If the version does not match, add it to the list of unfulfilled requirement options.
        required_any.append(str(dep))
        found_any.append(f"{req.name} {dist_version}")

    if is_dependency_conflict:
        return DependencyConflict(
            required_any=required_any,
            found_any=found_any,
        )
    return None
