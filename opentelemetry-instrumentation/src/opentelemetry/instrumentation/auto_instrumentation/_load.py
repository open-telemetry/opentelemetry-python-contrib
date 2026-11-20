# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import sys
from functools import cached_property
from logging import (
    CRITICAL,
    DEBUG,
    ERROR,
    INFO,
    WARNING,
    Formatter,
    Logger,
    LoggerAdapter,
    NullHandler,
    StreamHandler,
    getLogger,
)
from os import environ
from typing import TYPE_CHECKING, Any

from opentelemetry.instrumentation.dependencies import (
    DependencyConflictError,
    get_dist_dependency_conflicts,
)
from opentelemetry.instrumentation.distro import BaseDistro, DefaultDistro
from opentelemetry.instrumentation.environment_variables import (
    OTEL_PYTHON_CONFIGURATOR,
    OTEL_PYTHON_DISABLED_INSTRUMENTATIONS,
    OTEL_PYTHON_DISTRO,
)
from opentelemetry.instrumentation.version import __version__
from opentelemetry.util._importlib_metadata import (
    EntryPoint,
    distributions,
    entry_points,
)

SKIPPED_INSTRUMENTATIONS_WILDCARD = "*"
_OTEL_LOG_LEVELS = {
    "trace": DEBUG,
    "debug": DEBUG,
    "info": INFO,
    "warn": WARNING,
    "warning": WARNING,
    "error": ERROR,
    "fatal": CRITICAL,
    "critical": CRITICAL,
}
_STARTUP_LOG_FORMATTER = Formatter("%(message)s")

if TYPE_CHECKING:
    _LoggerAdapterBase = LoggerAdapter[Logger]
else:
    # LoggerAdapter is not subscriptable at runtime on Python 3.10.
    _LoggerAdapterBase = LoggerAdapter


class _StartupLoggerAdapter(_LoggerAdapterBase):
    """Print startup messages to stderr before the application sets up logging."""

    def __init__(self, logger: Logger) -> None:
        super().__init__(logger, {})
        self._log_to_stderr = False

    def initialize(self) -> None:
        self._log_to_stderr = not self._app_logging_already_configured()

    def log(self, level: int, msg: object, *args: object, **kwargs: Any) -> None:
        super().log(level, msg, *args, **kwargs)

        # Standard logging already handles warnings and errors through lastResort.
        if level >= WARNING or not self._log_to_stderr:
            return

        if environ.get("OTEL_CONFIG_FILE"):
            # If we're using declarative config, get the log level from the otel logger rather that from the env var.
            min_level = getLogger("opentelemetry").level or INFO
        else:
            min_level = _OTEL_LOG_LEVELS.get(environ.get("OTEL_LOG_LEVEL", "").strip().lower() or "info")

        if min_level is None or level < min_level:
            return

        startup_logger = Logger(self.logger.name, level)  # noqa: LOG001
        handler = StreamHandler(sys.stderr)
        handler.setFormatter(_STARTUP_LOG_FORMATTER)
        startup_logger.addHandler(handler)
        try:
            startup_logger.log(level, msg, *args, **kwargs)
        finally:
            handler.close()

    def _app_logging_already_configured(self) -> bool:
        if self.logger.disabled:
            return True
        logger: Logger | None = self.logger
        while logger:
            if any(not isinstance(handler, NullHandler) for handler in logger.handlers):
                return True
            if not logger.propagate:
                return True
            logger = logger.parent
        return False


_logger = _StartupLoggerAdapter(getLogger("opentelemetry.instrumentation.auto_instrumentation"))


class _EntryPointDistFinder:
    @cached_property
    def _mapping(self):
        return {self._key_for(ep): dist for dist in distributions() for ep in dist.entry_points}

    def dist_for(self, entry_point: EntryPoint):
        dist = getattr(entry_point, "dist", None)
        if dist:
            return dist

        return self._mapping.get(self._key_for(entry_point))

    @staticmethod
    def _key_for(entry_point: EntryPoint):
        return f"{entry_point.group}:{entry_point.name}:{entry_point.value}"


def _load_distro() -> BaseDistro:
    distro_name = environ.get(OTEL_PYTHON_DISTRO, None)
    for entry_point in entry_points(group="opentelemetry_distro"):
        try:
            # If no distro is specified, use first to come up.
            if distro_name is None or distro_name == entry_point.name:
                distro = entry_point.load()()
                if not isinstance(distro, BaseDistro):
                    _logger.debug(
                        "%s is not an OpenTelemetry Distro. Skipping",
                        entry_point.name,
                    )
                    continue
                _logger.debug(
                    "Loaded OpenTelemetry distribution: %s.%s",
                    type(distro).__module__,
                    type(distro).__qualname__,
                )
                return distro
        except Exception as exc:  # pylint: disable=broad-except
            _logger.exception("Distribution %s configuration failed", entry_point.name)
            raise exc
    return DefaultDistro()


def _load_instrumentors(distro):
    package_to_exclude = environ.get(OTEL_PYTHON_DISABLED_INSTRUMENTATIONS, [])
    entry_point_finder = _EntryPointDistFinder()
    if isinstance(package_to_exclude, str):
        package_to_exclude = package_to_exclude.split(",")
        # to handle users entering "requests , flask" or "requests, flask" with spaces
        package_to_exclude = [x.strip() for x in package_to_exclude]

    for entry_point in entry_points(group="opentelemetry_pre_instrument"):
        entry_point.load()()

    for entry_point in entry_points(group="opentelemetry_instrumentor"):
        if SKIPPED_INSTRUMENTATIONS_WILDCARD in package_to_exclude:
            break

        if entry_point.name in package_to_exclude:
            _logger.debug("Instrumentation skipped for library %s", entry_point.name)
            continue

        try:
            entry_point_dist = entry_point_finder.dist_for(entry_point)
            conflict = get_dist_dependency_conflicts(entry_point_dist)
            if conflict:
                conflict._log(_logger, entry_point.name)
                continue

            # tell instrumentation to not run dep checks again as we already did it above
            distro.load_instrumentor(entry_point, skip_dep_check=True)
            _logger.debug("Loaded OpenTelemetry instrumentation for %s", entry_point.name)
        except DependencyConflictError as exc:
            # Dependency conflicts are generally caught from get_dist_dependency_conflicts
            # returning a DependencyConflict. Keeping this error handling in case custom
            # distro and instrumentor behavior raises a DependencyConflictError later.
            # See https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3610
            exc.conflict._log(_logger, entry_point.name)
            continue
        except ModuleNotFoundError as exc:
            # ModuleNotFoundError is raised when the library is not installed
            # and the instrumentation is not required to be loaded.
            # See https://github.com/open-telemetry/opentelemetry-python-contrib/issues/3421
            _logger.debug("Skipping instrumentation %s: %s", entry_point.name, exc.msg)
            continue
        except ImportError:
            # in scenarios using the kubernetes operator to do autoinstrumentation some
            # instrumentors (usually requiring binary extensions) may fail to load
            # because the injected autoinstrumentation code does not match the application
            # environment regarding python version, libc, etc... In this case it's better
            # to skip the single instrumentation rather than failing to load everything
            # so treat differently ImportError than the rest of exceptions
            _logger.exception("Importing of %s failed, skipping it", entry_point.name)
            continue
        except Exception as exc:  # pylint: disable=broad-except
            _logger.exception("Instrumenting of %s failed", entry_point.name)
            raise exc

    for entry_point in entry_points(group="opentelemetry_post_instrument"):
        entry_point.load()()


def _load_configurators():
    configurator_name = environ.get(OTEL_PYTHON_CONFIGURATOR, None)
    configured = None
    for entry_point in entry_points(group="opentelemetry_configurator"):
        if configured is not None:
            _logger.warning(
                "Configuration of %s not loaded, %s already loaded",
                entry_point.name,
                configured,
            )
            continue
        try:
            if configurator_name is None or configurator_name == entry_point.name:
                entry_point.load()().configure(auto_instrumentation_version=__version__)  # type: ignore
                configured = entry_point.name
            else:
                _logger.warning(
                    "Configuration of %s not loaded because %s is set by %s",
                    entry_point.name,
                    configurator_name,
                    OTEL_PYTHON_CONFIGURATOR,
                )
        except Exception as exc:  # pylint: disable=broad-except
            _logger.exception("Configuration of %s failed", entry_point.name)
            raise exc
