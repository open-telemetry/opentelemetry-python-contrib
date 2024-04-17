from logging import getLogger
from typing import Collection, Optional

from packaging.requirements import Requirement, InvalidRequirement
from importlib.metadata import PackageNotFoundError, Distribution, version

logger = getLogger(__name__)


class DependencyConflict:
    required: str = None
    found: Optional[str] = None

    def __init__(self, required, found=None):
        self.required = required
        self.found = found

    def __str__(self):
        return f'DependencyConflict: requested: "{self.required}" but found: "{self.found}"'


def get_dist_dependency_conflicts(
    dist: Distribution,
) -> Optional[DependencyConflict]:
    instrumentation_deps = []
    extra = "extra"
    instruments = "instruments"
    instruments_marker = {extra: instruments}
    for dep in dist.requires:
        if extra not in dep or instruments not in dep:
            continue

        req = Requirement(dep)
        if req.marker.evaluate(instruments_marker):
            instrumentation_deps.append(req)

    return get_dependency_conflicts(instrumentation_deps)


def get_dependency_conflicts(
    deps: Collection[str, Requirement],
) -> Optional[DependencyConflict]:
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
