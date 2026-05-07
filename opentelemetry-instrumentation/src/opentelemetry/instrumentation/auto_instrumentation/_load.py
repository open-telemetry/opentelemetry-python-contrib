# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from functools import cached_property
from logging import DEBUG, NOTSET, Logger, LoggerAdapter, getLogger
from os import environ
from sys import stderr

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
OTEL_LOG_LEVEL = "OTEL_LOG_LEVEL"
_DEBUG_LOG_LEVELS = frozenset(("trace", "debug"))


def _otel_log_level_allows_debug() -> bool:
    log_level = environ.get(OTEL_LOG_LEVEL, "").strip().lower()
    return log_level in _DEBUG_LOG_LEVELS


def _format_log_arg(arg: object) -> object:
    if isinstance(arg, str):
        return repr(arg)

    return arg


class _OtelLogLevelLoggerAdapter(LoggerAdapter):
    """Write startup debug messages to stderr when logging would drop them.

    Auto-instrumentation usually runs from sitecustomize before the
    application configures logging, so normal logger.debug calls are often
    not visible even when OTEL_LOG_LEVEL=debug. This adapter keeps normal
    logging behavior, but also writes the same startup messages to stderr when
    OTEL_LOG_LEVEL asks for debug output and Python logging would not emit them.
    """

    def __init__(self, logger, extra):
        super().__init__(logger, extra)
        # This adapter is built when this module is imported. That covers the
        # sitecustomize path where auto-instrumentation runs before application
        # logging setup, and the edge case where Python logging is set up and then
        # auto_instrumentation.initialize() is invoked explicitly. If this adapter
        # is used after application code can change logging, it should be modified
        # to not use the cached value in the _logger_emits_debug field.
        self._logger_emits_debug = self._logger_would_emit(DEBUG)

    def debug(self, msg: str, *args: object, **kwargs: object) -> None:
        super().debug(msg, *args, **kwargs)

        if not _otel_log_level_allows_debug() or self._logger_emits_debug:
            return

        message = msg
        if args:
            message = message % tuple(_format_log_arg(arg) for arg in args)

        stderr.write(f"DEBUG:{self.logger.name}:{message}\n")
        stderr.flush()

    def _logger_would_emit(self, level: int) -> bool:
        # If the logger itself would reject this level, don't bother walking handlers.
        if not self.logger.isEnabledFor(level):
            return False

        logger: Logger | None = self.logger
        while logger:
            for handler in logger.handlers:
                if handler.level == NOTSET or level >= handler.level:
                    return True

            # If we get here, this logger's handlers would not emit the record.
            # If propagation is disabled, parent handlers will not see it either.
            if not logger.propagate:
                break

            logger = logger.parent

        return False


_logger = _OtelLogLevelLoggerAdapter(getLogger(__name__), {})


class _EntryPointDistFinder:
    @cached_property
    def _mapping(self):
        return {
            self._key_for(ep): dist
            for dist in distributions()
            for ep in dist.entry_points
        }

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
                    "Distribution %s will be configured", entry_point.name
                )
                return distro
        except Exception as exc:  # pylint: disable=broad-except
            _logger.exception(
                "Distribution %s configuration failed", entry_point.name
            )
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
            _logger.debug(
                "Instrumentation skipped for library %s", entry_point.name
            )
            continue

        try:
            entry_point_dist = entry_point_finder.dist_for(entry_point)
            conflict = get_dist_dependency_conflicts(entry_point_dist)
            if conflict:
                _logger.debug(
                    "Skipping instrumentation %s: %s",
                    entry_point.name,
                    conflict,
                )
                continue

            # tell instrumentation to not run dep checks again as we already did it above
            distro.load_instrumentor(entry_point, skip_dep_check=True)
            _logger.debug("Instrumented %s", entry_point.name)
        except DependencyConflictError as exc:
            # Dependency conflicts are generally caught from get_dist_dependency_conflicts
            # returning a DependencyConflict. Keeping this error handling in case custom
            # distro and instrumentor behavior raises a DependencyConflictError later.
            # See https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3610
            _logger.debug(
                "Skipping instrumentation %s: %s",
                entry_point.name,
                exc.conflict,
            )
            continue
        except ModuleNotFoundError as exc:
            # ModuleNotFoundError is raised when the library is not installed
            # and the instrumentation is not required to be loaded.
            # See https://github.com/open-telemetry/opentelemetry-python-contrib/issues/3421
            _logger.debug(
                "Skipping instrumentation %s: %s", entry_point.name, exc.msg
            )
            continue
        except ImportError:
            # in scenarios using the kubernetes operator to do autoinstrumentation some
            # instrumentors (usually requiring binary extensions) may fail to load
            # because the injected autoinstrumentation code does not match the application
            # environment regarding python version, libc, etc... In this case it's better
            # to skip the single instrumentation rather than failing to load everything
            # so treat differently ImportError than the rest of exceptions
            _logger.exception(
                "Importing of %s failed, skipping it", entry_point.name
            )
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
            if (
                configurator_name is None
                or configurator_name == entry_point.name
            ):
                entry_point.load()().configure(
                    auto_instrumentation_version=__version__
                )  # type: ignore
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
