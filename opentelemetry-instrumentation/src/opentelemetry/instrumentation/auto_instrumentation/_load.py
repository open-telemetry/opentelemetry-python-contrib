# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import sys
from functools import cached_property
from logging import (
    CRITICAL,
    DEBUG,
    ERROR,
    INFO,
    WARNING,
    Logger,
    LoggerAdapter,
    NullHandler,
    getLevelName,
    getLogger,
)
from os import environ

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


def _otel_log_level() -> int | None:
    log_level = environ.get(OTEL_LOG_LEVEL, "").strip().lower()
    return _OTEL_LOG_LEVELS.get(log_level)


def _format_log_message(msg: object, args: tuple[object, ...]) -> str:
    message = str(msg)
    if not args:
        return message

    try:
        return message % args
    except Exception:  # pylint: disable=broad-except
        return message


class _OtelLogLevelLoggerAdapter(LoggerAdapter):
    """Write startup log messages to stderr before logging is configured.

    Auto-instrumentation usually runs from sitecustomize before the
    application configures logging, so normal log calls are often not visible
    even when OTEL_LOG_LEVEL requests them. This adapter keeps normal logging
    behavior, but also writes startup messages to stderr when OTEL_LOG_LEVEL
    asks for that level and no application logging configuration is detected on
    the logger path. Once the application configures logging, its logger and
    handler settings determine what gets emitted. Warning and higher records
    are left to stdlib logging's lastResort handler so normal warning/error
    output is not duplicated.
    """

    def log(
        self, level: int, msg: object, *args: object, **kwargs: object
    ) -> None:
        # If application logging is already configured, make normal logging
        # report the _logger caller instead of this helper. e.g.:
        # DEBUG:_load.py:131:_load_instrumentors:Instrumented my_instrumentor
        # instead of:
        # DEBUG:_load.py:234:log:Instrumented my_instrumentor
        kwargs["stacklevel"] = kwargs.get("stacklevel", 1) + 1

        super().log(level, msg, *args, **kwargs)

        otel_log_level = _otel_log_level()
        if otel_log_level is None or level < otel_log_level:
            return

        if self._has_application_logging_configuration():
            return

        if self._handled_by_logging_last_resort(level):
            return

        message = _format_log_message(msg, args)
        sys.stderr.write(
            f"{getLevelName(level)}:{self.logger.name}:{message}\n"
        )
        sys.stderr.flush()

    @staticmethod
    def _handled_by_logging_last_resort(level: int) -> bool:
        return level >= WARNING

    def _has_application_logging_configuration(self) -> bool:
        logger: Logger | None = self.logger
        while logger:
            for handler in logger.handlers:
                if not isinstance(handler, NullHandler):
                    return True

            # Respect application logging configuration even if it prevents this
            # record from reaching a handler.
            if not logger.propagate:
                return True

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
