from logging import getLogger
from typing import Collection, Optional
import importlib_metadata
from packaging.requirements import Requirement
from packaging.version import parse as parse_version

logger = getLogger(__name__)


class DependencyConflict:
    required: str = None
    found: Optional[str] = None

    def __init__(self, required, found=None):
        self.required = required
        self.found = found

    def __str__(self):
        return f'DependencyConflict: requested: "{self.required}" but found: "{self.found}"'


def _check_version(conflict_requirement, installed_version):
    if not conflict_requirement.specifier.contains(installed_version, prereleases=True):
        return f"{conflict_requirement.name} {installed_version}"
    return None


def get_dependency_conflicts(
    deps: Collection[str],
) -> Optional[DependencyConflict]:
    for dep in deps:
        try:
            requirement = Requirement(dep)
            distribution = importlib_metadata.distribution(requirement.name)
            installed_version = parse_version(distribution.version)
            conflict_version = _check_version(requirement, installed_version)
            if conflict_version:
                return DependencyConflict(dep, conflict_version)
        except importlib_metadata.PackageNotFoundError:
            return DependencyConflict(dep)
        except Exception as exc:
            logger.warning(
                'error parsing dependency, reporting as a conflict: "%s" - %s',
                dep,
                exc,
            )
            return DependencyConflict(dep)
    return None


def get_dist_dependency_conflicts(
    dist_name: str,  # Assuming dist_name is the name of the distribution
) -> Optional[DependencyConflict]:
    try:
        distribution = importlib_metadata.distribution(dist_name)
    except importlib_metadata.PackageNotFoundError:
        return DependencyConflict(dist_name)

    conflicts = []
    for req in distribution.requires or []:
        try:
            requirement = Requirement(req)
            dep_dist = importlib_metadata.distribution(requirement.name)
            installed_version = parse_version(dep_dist.version)
            if not requirement.specifier.contains(installed_version, prereleases=True):
                conflicts.append(f"{requirement.name} {installed_version}")
        except importlib_metadata.PackageNotFoundError:
            conflicts.append(requirement.name)

    if conflicts:
        # Return the first conflict found for simplicity
        return DependencyConflict(str(conflicts[0]))
    return None
