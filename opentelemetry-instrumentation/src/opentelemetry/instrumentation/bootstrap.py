# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import argparse
import logging
import sys
from subprocess import (
    PIPE,
    CalledProcessError,
    Popen,
    SubprocessError,
    check_call,
)
from typing import Optional

from packaging.requirements import Requirement

from opentelemetry.instrumentation.bootstrap_gen import (
    default_instrumentations as gen_default_instrumentations,
)
from opentelemetry.instrumentation.bootstrap_gen import (
    libraries as gen_libraries,
)
from opentelemetry.instrumentation.version import __version__
from opentelemetry.util._importlib_metadata import (
    PackageNotFoundError,
    version,
)

logger = logging.getLogger(__name__)


def _syscall(func):
    def wrapper(packages=None, upgrade=True):
        try:
            if packages:
                return func(packages, upgrade)
            return func()
        except SubprocessError as exp:
            cmd = getattr(exp, "cmd", None)
            if cmd:
                msg = f'Error calling system command "{" ".join(cmd)}"'
            if packages:
                msg = f'{msg} for package "{packages}"'
            raise RuntimeError(msg)

    return wrapper


@_syscall
def _sys_pip_install(packages, upgrade=True):
    # explicit upgrade strategy to override potential pip config
    try:
        cmd = [sys.executable, "-m", "pip", "install"]
        if upgrade:
            cmd += ["-U", "--upgrade-strategy", "only-if-needed"]
        cmd += [*packages]
        check_call(cmd)
    except CalledProcessError as error:
        print(error)


def _pip_check(libraries):
    """Ensures none of the instrumentations have dependency conflicts.
    Clean check reported as:
    'No broken requirements found.'
    Dependency conflicts are reported as:
    'opentelemetry-instrumentation-flask 1.0.1 has requirement opentelemetry-sdk<2.0,>=1.0, but you have opentelemetry-sdk 0.5.'
    To not be too restrictive, we'll only check for relevant packages.
    """
    with Popen(
        [sys.executable, "-m", "pip", "check"], stdout=PIPE
    ) as check_pipe:
        pip_check = check_pipe.communicate()[0].decode()
        pip_check_lower = pip_check.lower()
    for package_tup in libraries:
        for package in package_tup:
            if package.lower() in pip_check_lower:
                raise RuntimeError(f"Dependency conflict found: {pip_check}")


def _is_installed(req):
    req = Requirement(req)

    try:
        dist_version = version(req.name)
    except PackageNotFoundError:
        return False

    if not req.specifier.filter(dist_version):
        logger.warning(
            "instrumentation for package %s is available"
            " but version %s is installed. Skipping.",
            req,
            dist_version,
        )
        return False
    return True


def _find_installed_libraries(default_instrumentations, libraries):
    yield from default_instrumentations

    for lib in libraries:
        if _is_installed(lib["library"]):
            yield lib["instrumentation"]


def _run_requirements(default_instrumentations, libraries):
    logger.setLevel(logging.ERROR)
    print(
        "\n".join(
            _find_installed_libraries(default_instrumentations, libraries)
        )
    )


def _run_install(default_instrumentations, libraries, upgrade=True):
    libs = list(_find_installed_libraries(default_instrumentations, libraries))
    if libs:
        _sys_pip_install(libs, upgrade=upgrade)
    _pip_check(libraries)


def run(
    default_instrumentations: Optional[list] = None,
    libraries: Optional[list] = None,
) -> None:
    action_install = "install"
    action_requirements = "requirements"

    parser = argparse.ArgumentParser(
        description="""
        opentelemetry-bootstrap detects installed libraries and automatically
        installs the relevant instrumentation packages for them.
        """
    )
    parser.add_argument(
        "--version",
        help="print version information",
        action="version",
        version="%(prog)s " + __version__,
    )
    parser.add_argument(
        "-a",
        "--action",
        choices=[action_install, action_requirements],
        default=action_requirements,
        help="""
        install - uses pip to install the new requirements using to the
                  currently active site-package.
        requirements - prints out the new requirements to stdout. Action can
                       be piped and appended to a requirements.txt file.
        """,
    )
    parser.add_argument(
        "--no-upgrade",
        action="store_true",
        help="Do not upgrade packages with -U flag during install",
    )
    args = parser.parse_args()

    if libraries is None:
        libraries = gen_libraries

    if default_instrumentations is None:
        default_instrumentations = gen_default_instrumentations

    if args.action == action_install:
        _run_install(
            default_instrumentations, libraries, upgrade=not args.no_upgrade
        )
    else:
        _run_requirements(default_instrumentations, libraries)
