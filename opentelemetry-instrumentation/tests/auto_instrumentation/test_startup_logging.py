# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
import os
from contextlib import redirect_stderr
from io import StringIO
from unittest import TestCase
from unittest.mock import patch

from opentelemetry.instrumentation.auto_instrumentation import _load


@patch.dict(os.environ, {"OTEL_LOG_LEVEL": "debug"}, clear=True)
class TestStartupLogging(TestCase):
    def setUp(self) -> None:
        self.parent = logging.getLogger("startup")
        self.logger = logging.getLogger("startup.loader")
        for logger, parent, level in (
            (self.parent, None, logging.WARNING),
            (self.logger, self.parent, logging.NOTSET),
        ):
            state = patch.multiple(
                logger,
                handlers=[],
                filters=[],
                parent=parent,
                level=level,
                propagate=True,
                disabled=False,
            )
            self.addCleanup(logger.setLevel, logger.level)
            self.addCleanup(state.stop)
            state.start()
            logger.setLevel(level)
        self.adapter = _load._StartupLoggerAdapter(self.logger)
        self.adapter.initialize()
        self.stderr = StringIO()

    def test_environment_level_controls_fallback(self) -> None:
        for value, expected in (
            ("debug", "Debug\nInfo\n"),
            ("trace", "Debug\nInfo\n"),
            (" DEBUG ", "Debug\nInfo\n"),
            ("TrAcE", "Debug\nInfo\n"),
            ("", "Info\n"),
            ("info", "Info\n"),
            ("warn", ""),
            ("warning", ""),
            ("error", ""),
            ("debug2", ""),
            ("unknown", ""),
        ):
            with self.subTest(value=value), patch.dict(os.environ, {"OTEL_LOG_LEVEL": value}):
                stderr = StringIO()
                with redirect_stderr(stderr):
                    self.adapter.debug("Debug")
                    self.adapter.info("Info")
                self.assertEqual(stderr.getvalue(), expected)

    def test_info_is_enabled_by_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True), redirect_stderr(self.stderr):
            self.adapter.info("Initialization completed")
            self.adapter.debug("Loaded OpenTelemetry instrumentation for requests")
        self.assertEqual(self.stderr.getvalue(), "Initialization completed\n")

    def test_declarative_level_controls_fallback_instead_of_environment_level(self) -> None:
        otel_logger = logging.getLogger("opentelemetry")
        self.addCleanup(otel_logger.setLevel, otel_logger.level)
        for config_level, env_level, expected in (
            (logging.DEBUG, "warn", "Loaded OpenTelemetry instrumentation for requests\nInitialization completed\n"),
            (logging.WARNING, "debug", ""),
        ):
            with (
                self.subTest(config_level=config_level),
                patch.dict(os.environ, {"OTEL_CONFIG_FILE": "config.yaml", "OTEL_LOG_LEVEL": env_level}),
            ):
                otel_logger.setLevel(config_level)
                stderr = StringIO()
                with redirect_stderr(stderr):
                    self.adapter.debug("Loaded OpenTelemetry instrumentation for requests")
                    self.adapter.info("Initialization completed")
                self.assertEqual(stderr.getvalue(), expected)

    def test_declarative_configuration_without_a_level_defaults_to_info(self) -> None:
        otel_logger = logging.getLogger("opentelemetry")
        self.addCleanup(otel_logger.setLevel, otel_logger.level)
        otel_logger.setLevel(logging.NOTSET)
        with patch.dict(os.environ, {"OTEL_CONFIG_FILE": "config.yaml"}), redirect_stderr(self.stderr):
            self.adapter.debug("Loaded OpenTelemetry instrumentation for requests")
            self.adapter.info("Initialization completed")
        self.assertEqual(self.stderr.getvalue(), "Initialization completed\n")

    def test_fallback_uses_standard_logging_arguments(self) -> None:
        with redirect_stderr(self.stderr):
            self.adapter.debug(
                "Loaded OpenTelemetry instrumentation for %(name)s",
                {"name": "requests"},
                extra={"instrumentor": "requests"},
            )
            try:
                raise ValueError("startup failure")
            except ValueError:
                self.adapter.debug("Details", exc_info=True)
            self.adapter.debug("Stack", stack_info=True)
        output = self.stderr.getvalue()
        self.assertIn("Loaded OpenTelemetry instrumentation for requests\n", output)
        self.assertIn("Details\nTraceback", output)
        self.assertIn("ValueError: startup failure", output)
        self.assertIn("Stack\nStack (most recent call last):", output)

    def test_bad_format_does_not_abort_startup(self) -> None:
        with redirect_stderr(self.stderr):
            self.adapter.debug("%s %s", "requests")
            self.adapter.debug("Startup continued")
        self.assertIn("Startup continued\n", self.stderr.getvalue())

    def test_fallback_does_not_change_application_logger_settings(self) -> None:
        with redirect_stderr(self.stderr):
            self.adapter.debug("First")
            self.adapter.debug("Second")
        self.assertEqual(self.logger.handlers, [])
        self.assertEqual(self.parent.handlers, [])
        self.assertEqual(self.logger.level, logging.NOTSET)
        self.assertEqual(self.parent.level, logging.WARNING)
        self.assertTrue(self.logger.propagate)
        self.assertEqual(self.stderr.getvalue(), "First\nSecond\n")

    def test_null_handler_allows_fallback(self) -> None:
        self.parent.addHandler(logging.NullHandler())
        self.adapter.initialize()
        with redirect_stderr(self.stderr):
            self.adapter.debug("Startup")
        self.assertEqual(self.stderr.getvalue(), "Startup\n")

    def test_application_handler_controls_output_even_when_it_drops_debug(self) -> None:
        for owner in (self.logger, self.parent):
            for level, expected in ((logging.DEBUG, "Startup\n"), (logging.WARNING, "")):
                with self.subTest(owner=owner.name, level=level):
                    output = StringIO()
                    handler = logging.StreamHandler(output)
                    self.addCleanup(handler.close)
                    handler.setLevel(level)
                    owner.addHandler(handler)
                    self.parent.setLevel(logging.DEBUG)
                    self.adapter.initialize()
                    with redirect_stderr(self.stderr):
                        self.adapter.debug("Startup")
                    self.assertEqual(self.stderr.getvalue(), "")
                    self.assertEqual(output.getvalue(), expected)
                    owner.removeHandler(handler)

    def test_application_handler_filters_control_output(self) -> None:
        handler = logging.StreamHandler(StringIO())
        self.addCleanup(handler.close)
        handler.addFilter(lambda record: False)
        self.parent.addHandler(handler)
        self.parent.setLevel(logging.DEBUG)
        self.adapter.initialize()
        with redirect_stderr(self.stderr):
            self.adapter.debug("Startup")
        self.assertEqual(self.stderr.getvalue(), "")

    def test_application_logging_is_checked_for_each_initialization(self) -> None:
        output = StringIO()
        handler = logging.StreamHandler(output)
        self.addCleanup(handler.close)
        with redirect_stderr(self.stderr):
            self.adapter.debug("Before")
            self.parent.addHandler(handler)
            self.parent.setLevel(logging.DEBUG)
            self.adapter.initialize()
            self.adapter.debug("After")
        self.assertEqual(self.stderr.getvalue(), "Before\n")
        self.assertEqual(output.getvalue(), "After\n")

    def test_application_handler_installed_during_startup_can_duplicate_messages(self) -> None:
        output = StringIO()
        handler = logging.StreamHandler(output)
        self.addCleanup(handler.close)
        with redirect_stderr(self.stderr):
            self.adapter.debug("Before")
            self.parent.addHandler(handler)
            self.parent.setLevel(logging.DEBUG)
            self.adapter.debug("After")
        self.assertEqual(self.stderr.getvalue(), "Before\nAfter\n")
        self.assertEqual(output.getvalue(), "After\n")

    def test_propagation_stop_controls_output(self) -> None:
        self.logger.propagate = False
        self.adapter.initialize()
        with redirect_stderr(self.stderr):
            self.adapter.debug("Startup")
        self.assertEqual(self.stderr.getvalue(), "")

    def test_disabled_logger_controls_output(self) -> None:
        self.logger.disabled = True
        self.adapter.initialize()
        with redirect_stderr(self.stderr):
            self.adapter.debug("Startup")
        self.assertEqual(self.stderr.getvalue(), "")

    def test_global_disable_controls_output(self) -> None:
        self.addCleanup(logging.disable, logging.root.manager.disable)
        logging.disable(logging.CRITICAL)
        with redirect_stderr(self.stderr):
            self.adapter.debug("Startup")
        self.assertEqual(self.stderr.getvalue(), "")

    def test_warning_and_error_use_normal_last_resort_output_once(self) -> None:
        with redirect_stderr(self.stderr):
            self.adapter.warning("Warning")
            self.adapter.error("Error")
        self.assertEqual(self.stderr.getvalue(), "Warning\nError\n")
