# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
# type: ignore

from contextlib import redirect_stderr
from io import StringIO
from logging import DEBUG, INFO, NOTSET, NullHandler, StreamHandler, getLogger
from unittest import TestCase
from unittest.mock import Mock, call, patch

from opentelemetry.instrumentation.auto_instrumentation import _load
from opentelemetry.instrumentation.dependencies import (
    DependencyConflict,
)
from opentelemetry.instrumentation.environment_variables import (
    OTEL_PYTHON_CONFIGURATOR,
    OTEL_PYTHON_DISABLED_INSTRUMENTATIONS,
    OTEL_PYTHON_DISTRO,
)
from opentelemetry.instrumentation.version import __version__
from opentelemetry.util._importlib_metadata import EntryPoint, entry_points

_AUTO_INSTRUMENTATION_LOAD_LOGGER_NAME = (
    "opentelemetry.instrumentation.auto_instrumentation._load"
)


class TestLoad(TestCase):
    @patch.dict(
        "os.environ", {OTEL_PYTHON_CONFIGURATOR: "custom_configurator2"}
    )
    @patch(
        "opentelemetry.instrumentation.auto_instrumentation._load.entry_points"
    )
    def test_load_configurators(self, iter_mock):  # pylint: disable=no-self-use
        # Add multiple entry points but only specify the 2nd in the environment variable.
        ep_mock1 = Mock()
        ep_mock1.name = "custom_configurator1"
        configurator_mock1 = Mock()
        ep_mock1.load.return_value = configurator_mock1
        ep_mock2 = Mock()
        ep_mock2.name = "custom_configurator2"
        configurator_mock2 = Mock()
        ep_mock2.load.return_value = configurator_mock2
        ep_mock3 = Mock()
        ep_mock3.name = "custom_configurator3"
        configurator_mock3 = Mock()
        ep_mock3.load.return_value = configurator_mock3

        iter_mock.return_value = (ep_mock1, ep_mock2, ep_mock3)
        _load._load_configurators()
        configurator_mock1.assert_not_called()
        configurator_mock2().configure.assert_called_once_with(
            auto_instrumentation_version=__version__
        )
        configurator_mock3.assert_not_called()

    @patch.dict(
        "os.environ", {OTEL_PYTHON_CONFIGURATOR: "custom_configurator2"}
    )
    @patch(
        "opentelemetry.instrumentation.auto_instrumentation._load.entry_points"
    )
    def test_load_configurators_no_ep(self, iter_mock):  # pylint: disable=no-self-use
        iter_mock.return_value = ()
        # Confirm method does not crash if not entry points exist.
        _load._load_configurators()

    @patch.dict(
        "os.environ", {OTEL_PYTHON_CONFIGURATOR: "custom_configurator2"}
    )
    @patch(
        "opentelemetry.instrumentation.auto_instrumentation._load.entry_points"
    )
    def test_load_configurators_error(self, iter_mock):
        # Add multiple entry points but only specify the 2nd in the environment variable.
        ep_mock1 = Mock()
        ep_mock1.name = "custom_configurator1"
        configurator_mock1 = Mock()
        ep_mock1.load.return_value = configurator_mock1
        ep_mock2 = Mock()
        ep_mock2.name = "custom_configurator2"
        configurator_mock2 = Mock()
        configurator_mock2().configure.side_effect = Exception()
        ep_mock2.load.return_value = configurator_mock2
        ep_mock3 = Mock()
        ep_mock3.name = "custom_configurator3"
        configurator_mock3 = Mock()
        ep_mock3.load.return_value = configurator_mock3

        iter_mock.return_value = (ep_mock1, ep_mock2, ep_mock3)
        # Confirm failed configuration raises exception.
        self.assertRaises(Exception, _load._load_configurators)

    @patch.dict("os.environ", {OTEL_PYTHON_DISTRO: "custom_distro2"})
    @patch(
        "opentelemetry.instrumentation.auto_instrumentation._load.isinstance"
    )
    @patch(
        "opentelemetry.instrumentation.auto_instrumentation._load.entry_points"
    )
    def test_load_distro(self, iter_mock, isinstance_mock):
        # Add multiple entry points but only specify the 2nd in the environment variable.
        ep_mock1 = Mock()
        ep_mock1.name = "custom_distro1"
        distro_mock1 = Mock()
        ep_mock1.load.return_value = distro_mock1
        ep_mock2 = Mock()
        ep_mock2.name = "custom_distro2"
        distro_mock2 = Mock()
        ep_mock2.load.return_value = distro_mock2
        ep_mock3 = Mock()
        ep_mock3.name = "custom_distro3"
        distro_mock3 = Mock()
        ep_mock3.load.return_value = distro_mock3

        iter_mock.return_value = (ep_mock1, ep_mock2, ep_mock3)
        # Mock entry points to be instances of BaseDistro.
        isinstance_mock.return_value = True
        self.assertEqual(
            _load._load_distro(),
            distro_mock2(),
        )

    @patch.dict("os.environ", {OTEL_PYTHON_DISTRO: "custom_distro2"})
    @patch(
        "opentelemetry.instrumentation.auto_instrumentation._load.isinstance"
    )
    @patch(
        "opentelemetry.instrumentation.auto_instrumentation._load.DefaultDistro"
    )
    @patch(
        "opentelemetry.instrumentation.auto_instrumentation._load.entry_points"
    )
    def test_load_distro_not_distro(
        self, iter_mock, default_distro_mock, isinstance_mock
    ):
        # Add multiple entry points but only specify the 2nd in the environment variable.
        ep_mock1 = Mock()
        ep_mock1.name = "custom_distro1"
        distro_mock1 = Mock()
        ep_mock1.load.return_value = distro_mock1
        ep_mock2 = Mock()
        ep_mock2.name = "custom_distro2"
        distro_mock2 = Mock()
        ep_mock2.load.return_value = distro_mock2
        ep_mock3 = Mock()
        ep_mock3.name = "custom_distro3"
        distro_mock3 = Mock()
        ep_mock3.load.return_value = distro_mock3

        iter_mock.return_value = (ep_mock1, ep_mock2, ep_mock3)
        # Confirm default distro is used if specified entry point is not a BaseDistro
        isinstance_mock.return_value = False
        self.assertEqual(
            _load._load_distro(),
            default_distro_mock(),
        )

    @patch.dict("os.environ", {OTEL_PYTHON_DISTRO: "custom_distro2"})
    @patch(
        "opentelemetry.instrumentation.auto_instrumentation._load.DefaultDistro"
    )
    @patch(
        "opentelemetry.instrumentation.auto_instrumentation._load.entry_points"
    )
    def test_load_distro_no_ep(self, iter_mock, default_distro_mock):
        iter_mock.return_value = ()
        # Confirm default distro is used if there are no entry points.
        self.assertEqual(
            _load._load_distro(),
            default_distro_mock(),
        )

    @patch.dict("os.environ", {OTEL_PYTHON_DISTRO: "custom_distro2"})
    @patch(
        "opentelemetry.instrumentation.auto_instrumentation._load.isinstance"
    )
    @patch(
        "opentelemetry.instrumentation.auto_instrumentation._load.entry_points"
    )
    def test_load_distro_error(self, iter_mock, isinstance_mock):
        ep_mock1 = Mock()
        ep_mock1.name = "custom_distro1"
        distro_mock1 = Mock()
        ep_mock1.load.return_value = distro_mock1
        ep_mock2 = Mock()
        ep_mock2.name = "custom_distro2"
        distro_mock2 = Mock()
        distro_mock2.side_effect = Exception()
        ep_mock2.load.return_value = distro_mock2
        ep_mock3 = Mock()
        ep_mock3.name = "custom_distro3"
        distro_mock3 = Mock()
        ep_mock3.load.return_value = distro_mock3

        iter_mock.return_value = (ep_mock1, ep_mock2, ep_mock3)
        isinstance_mock.return_value = True
        # Confirm method raises exception if it fails to load a distro.
        self.assertRaises(Exception, _load._load_distro)

    @staticmethod
    def _instrumentation_failed_to_load_call(entry_point, dependency_conflict):
        return call(
            "Skipping instrumentation %s: %s", entry_point, dependency_conflict
        )

    @patch.dict(
        "os.environ",
        {OTEL_PYTHON_DISABLED_INSTRUMENTATIONS: " instr1 , instr3 "},
    )
    @patch(
        "opentelemetry.instrumentation.auto_instrumentation._load.get_dist_dependency_conflicts"
    )
    @patch(
        "opentelemetry.instrumentation.auto_instrumentation._load.entry_points"
    )
    def test_load_instrumentors(self, iter_mock, mock_dep):
        # Mock opentelemetry_pre_instrument entry points
        # pylint: disable=too-many-locals
        pre_ep_mock1 = Mock()
        pre_ep_mock1.name = "pre1"
        pre_mock1 = Mock()
        pre_ep_mock1.load.return_value = pre_mock1

        pre_ep_mock2 = Mock()
        pre_ep_mock2.name = "pre2"
        pre_mock2 = Mock()
        pre_ep_mock2.load.return_value = pre_mock2

        # Mock opentelemetry_instrumentor entry points
        ep_mock1 = Mock()
        ep_mock1.name = "instr1"

        ep_mock2 = Mock()
        ep_mock2.name = "instr2"

        ep_mock3 = Mock()
        ep_mock3.name = "instr3"

        ep_mock4 = Mock()
        ep_mock4.name = "instr4"

        # Mock opentelemetry_instrumentor entry points
        post_ep_mock1 = Mock()
        post_ep_mock1.name = "post1"
        post_mock1 = Mock()
        post_ep_mock1.load.return_value = post_mock1

        post_ep_mock2 = Mock()
        post_ep_mock2.name = "post2"
        post_mock2 = Mock()
        post_ep_mock2.load.return_value = post_mock2

        distro_mock = Mock()

        # Mock entry points in order
        iter_mock.side_effect = [
            (pre_ep_mock1, pre_ep_mock2),
            (ep_mock1, ep_mock2, ep_mock3, ep_mock4),
            (post_ep_mock1, post_ep_mock2),
        ]
        # No dependency conflict
        mock_dep.return_value = None
        _load._load_instrumentors(distro_mock)
        # All opentelemetry_pre_instrument entry points should be loaded
        pre_mock1.assert_called_once()
        pre_mock2.assert_called_once()
        self.assertEqual(iter_mock.call_count, 3)
        # Only non-disabled instrumentations should be loaded
        distro_mock.load_instrumentor.assert_has_calls(
            [
                call(ep_mock2, skip_dep_check=True),
                call(ep_mock4, skip_dep_check=True),
            ]
        )
        self.assertEqual(distro_mock.load_instrumentor.call_count, 2)
        # All opentelemetry_post_instrument entry points should be loaded
        post_mock1.assert_called_once()
        post_mock2.assert_called_once()

    @patch.dict(
        "os.environ",
        {OTEL_PYTHON_DISABLED_INSTRUMENTATIONS: " instr1 , instr3 "},
    )
    @patch(
        "opentelemetry.instrumentation.auto_instrumentation._load.get_dist_dependency_conflicts"
    )
    @patch("opentelemetry.instrumentation.auto_instrumentation._load._logger")
    @patch(
        "opentelemetry.instrumentation.auto_instrumentation._load.entry_points"
    )
    def test_load_instrumentors_dep_conflict(
        self, iter_mock, mock_logger, mock_dep
    ):  # pylint: disable=no-self-use
        ep_mock1 = Mock()
        ep_mock1.name = "instr1"  # disabled

        ep_mock2 = Mock()
        ep_mock2.name = "instr2"

        ep_mock3 = Mock()
        ep_mock3.name = "instr3"  # disabled

        ep_mock4 = Mock()
        ep_mock4.name = "instr4"  # dependency conflict

        dependency_conflict = DependencyConflict("1.2.3", None)

        distro_mock = Mock()

        iter_mock.return_value = (ep_mock1, ep_mock2, ep_mock3, ep_mock4)
        print((ep_mock1, ep_mock2, ep_mock3, ep_mock4))
        # If a dependency conflict is raised, that instrumentation should not be loaded, but others still should.
        # In this case, ep_mock4 will not be loaded and ep_mock2 will succeed. (ep_mock1 and ep_mock3 are disabled)
        mock_dep.side_effect = [None, dependency_conflict]
        _load._load_instrumentors(distro_mock)
        distro_mock.load_instrumentor.assert_has_calls(
            [
                call(ep_mock2, skip_dep_check=True),
            ]
        )
        distro_mock.load_instrumentor.assert_called_once()
        mock_logger.debug.assert_has_calls(
            [
                call(
                    "Instrumentation skipped for library %s",
                    ep_mock1.name,
                ),
                call("Instrumented %s", ep_mock2.name),
                call(
                    "Instrumentation skipped for library %s",
                    ep_mock3.name,
                ),
                self._instrumentation_failed_to_load_call(
                    ep_mock4.name,
                    dependency_conflict,
                ),
            ]
        )

    @patch(
        "opentelemetry.instrumentation.auto_instrumentation._load.get_dist_dependency_conflicts"
    )
    @patch("opentelemetry.instrumentation.auto_instrumentation._load._logger")
    @patch(
        "opentelemetry.instrumentation.auto_instrumentation._load.entry_points"
    )
    def test_load_instrumentors_import_error_does_not_stop_everything(
        self, iter_mock, mock_logger, mock_dep
    ):
        ep_mock1 = Mock(name="instr1")
        ep_mock2 = Mock(name="instr2")

        distro_mock = Mock()
        distro_mock.load_instrumentor.side_effect = [ImportError, None]

        # Mock entry points in order
        iter_mock.side_effect = [
            (),
            (ep_mock1, ep_mock2),
            (),
        ]
        mock_dep.return_value = None

        _load._load_instrumentors(distro_mock)

        distro_mock.load_instrumentor.assert_has_calls(
            [
                call(ep_mock1, skip_dep_check=True),
                call(ep_mock2, skip_dep_check=True),
            ]
        )
        self.assertEqual(distro_mock.load_instrumentor.call_count, 2)
        mock_logger.exception.assert_any_call(
            "Importing of %s failed, skipping it",
            ep_mock1.name,
        )

        mock_logger.debug.assert_any_call("Instrumented %s", ep_mock2.name)

    @patch(
        "opentelemetry.instrumentation.auto_instrumentation._load.get_dist_dependency_conflicts"
    )
    @patch(
        "opentelemetry.instrumentation.auto_instrumentation._load.entry_points"
    )
    def test_load_instrumentors_raises_exception(self, iter_mock, mock_dep):
        ep_mock1 = Mock(name="instr1")
        ep_mock2 = Mock(name="instr2")

        distro_mock = Mock()
        distro_mock.load_instrumentor.side_effect = [ValueError, None]

        # Mock entry points in order
        iter_mock.side_effect = [
            (),
            (ep_mock1, ep_mock2),
            (),
        ]
        mock_dep.return_value = None

        with self.assertRaises(ValueError):
            _load._load_instrumentors(distro_mock)

        distro_mock.load_instrumentor.assert_has_calls(
            [
                call(ep_mock1, skip_dep_check=True),
            ]
        )
        self.assertEqual(distro_mock.load_instrumentor.call_count, 1)

    @patch(
        "opentelemetry.instrumentation.auto_instrumentation._load.get_dist_dependency_conflicts"
    )
    @patch("opentelemetry.instrumentation.auto_instrumentation._load._logger")
    @patch(
        "opentelemetry.instrumentation.auto_instrumentation._load.entry_points"
    )
    def test_load_instrumentors_module_not_found_error(
        self, iter_mock, mock_logger, mock_dep
    ):
        ep_mock1 = Mock()
        ep_mock1.name = "instr1"

        ep_mock2 = Mock()
        ep_mock2.name = "instr2"

        distro_mock = Mock()

        mock_dep.return_value = None

        distro_mock.load_instrumentor.side_effect = [
            ModuleNotFoundError("No module named 'fake_module'"),
            None,
        ]

        iter_mock.side_effect = [(), (ep_mock1, ep_mock2), ()]

        _load._load_instrumentors(distro_mock)

        distro_mock.load_instrumentor.assert_has_calls(
            [
                call(ep_mock1, skip_dep_check=True),
                call(ep_mock2, skip_dep_check=True),
            ]
        )
        self.assertEqual(distro_mock.load_instrumentor.call_count, 2)

        mock_logger.debug.assert_any_call(
            "Skipping instrumentation %s: %s",
            "instr1",
            "No module named 'fake_module'",
        )

        mock_logger.debug.assert_any_call("Instrumented %s", ep_mock2.name)

    def test_load_instrumentors_no_entry_point_mocks(self):
        distro_mock = Mock()
        _load._load_instrumentors(distro_mock)
        # this has no specific assert because it is run for every instrumentation
        self.assertTrue(distro_mock)

    def test_entry_point_dist_finder(self):
        entry_point_finder = _load._EntryPointDistFinder()
        self.assertTrue(entry_point_finder._mapping)
        entry_point = list(
            entry_points(group="opentelemetry_environment_variables")
        )[0]
        self.assertTrue(entry_point)
        self.assertTrue(entry_point.dist)

        # this will not hit cache
        entry_point_dist = entry_point_finder.dist_for(entry_point)
        self.assertTrue(entry_point_dist)
        # dist are not comparable so we are sure we are not hitting the cache
        self.assertEqual(entry_point.dist, entry_point_dist)

        # this will hit cache
        entry_point_without_dist = EntryPoint(
            name=entry_point.name,
            group=entry_point.group,
            value=entry_point.value,
        )
        self.assertIsNone(entry_point_without_dist.dist)
        new_entry_point_dist = entry_point_finder.dist_for(
            entry_point_without_dist
        )
        # dist are not comparable, being truthy is enough
        self.assertTrue(new_entry_point_dist)

    @patch.dict(
        "os.environ",
        {OTEL_PYTHON_DISABLED_INSTRUMENTATIONS: "*"},
    )
    @patch(
        "opentelemetry.instrumentation.auto_instrumentation._load.get_dist_dependency_conflicts"
    )
    @patch(
        "opentelemetry.instrumentation.auto_instrumentation._load.entry_points"
    )
    def test_no_instrumentor_called_with_wildcard(self, iter_mock, mock_dep):
        # Mock opentelemetry_pre_instrument entry points
        # pylint: disable=too-many-locals
        pre_ep_mock1 = Mock()
        pre_ep_mock1.name = "pre1"
        pre_mock1 = Mock()
        pre_ep_mock1.load.return_value = pre_mock1

        # Mock opentelemetry_instrumentor entry points
        ep_mock1 = Mock()
        ep_mock1.name = "instr1"

        # Mock opentelemetry_instrumentor entry points
        post_ep_mock1 = Mock()
        post_ep_mock1.name = "post1"
        post_mock1 = Mock()
        post_ep_mock1.load.return_value = post_mock1

        distro_mock = Mock()

        # Mock entry points in order
        iter_mock.side_effect = [
            (pre_ep_mock1,),
            (ep_mock1,),
            (post_ep_mock1,),
        ]
        _load._load_instrumentors(distro_mock)

        self.assertEqual(iter_mock.call_count, 3)

        # All opentelemetry_pre_instrument entry points should be loaded
        pre_mock1.assert_called_once()

        # No instrumentations should be loaded
        mock_dep.assert_not_called()
        distro_mock.load_instrumentor.assert_not_called()
        self.assertEqual(distro_mock.load_instrumentor.call_count, 0)

        # All opentelemetry_post_instrument entry points should be loaded
        post_mock1.assert_called_once()


class TestOtelLogLevelLogger(TestCase):
    @staticmethod
    def _logger_mock(name=_AUTO_INSTRUMENTATION_LOAD_LOGGER_NAME):
        logger_mock = Mock()
        logger_mock.isEnabledFor.return_value = True
        logger_mock.handlers = []
        logger_mock.parent = None
        logger_mock.propagate = True
        logger_mock.name = name
        return logger_mock

    @staticmethod
    def _expected_message(
        message, name=_AUTO_INSTRUMENTATION_LOAD_LOGGER_NAME
    ):
        return "DEBUG:" + name + ":" + message + "\n"

    @staticmethod
    def _stderr_from_debug(logger):
        stderr = StringIO()
        with redirect_stderr(stderr):
            logger.debug("Instrumented %s", "requests")
        return stderr.getvalue()

    def _save_logger_state(self, logger):
        state = (
            logger.handlers[:],
            logger.level,
            logger.propagate,
            logger.disabled,
        )
        self.addCleanup(self._restore_logger_state, logger, state)

    @staticmethod
    def _restore_logger_state(logger, state):
        handlers, level, propagate, disabled = state
        logger.handlers = handlers
        logger.setLevel(level)
        logger.propagate = propagate
        logger.disabled = disabled

    def test_writes_otel_log_level_output_for_debug_levels(self):
        for log_level in ("debug", "trace"):
            with (
                self.subTest(log_level=log_level),
                patch.dict(
                    "os.environ", {"OTEL_LOG_LEVEL": log_level}, clear=True
                ),
            ):
                logger_mock = self._logger_mock()
                logger = _load._OtelLogLevelLoggerAdapter(logger_mock, {})

                self.assertEqual(
                    self._stderr_from_debug(logger),
                    self._expected_message("Instrumented 'requests'"),
                )

                logger_mock.log.assert_called_once_with(
                    DEBUG, "Instrumented %s", "requests", extra={}
                )

    def test_writes_otel_log_level_output_to_current_sys_stderr(self):
        with patch.dict("os.environ", {"OTEL_LOG_LEVEL": "debug"}, clear=True):
            logger = _load._OtelLogLevelLoggerAdapter(self._logger_mock(), {})
            stderr = StringIO()

            with redirect_stderr(stderr):
                logger.debug("Instrumented %s", "requests")

            self.assertEqual(
                stderr.getvalue(),
                self._expected_message("Instrumented 'requests'"),
            )

    @patch.dict("os.environ", {"OTEL_LOG_LEVEL": "debug"}, clear=True)
    def test_otel_log_level_output_does_not_crash_on_format_error(self):
        logger = _load._OtelLogLevelLoggerAdapter(self._logger_mock(), {})
        msg = "Instrumented %s %s"
        stderr = StringIO()

        with redirect_stderr(stderr):
            logger.debug(msg, "requests")

        self.assertEqual(
            stderr.getvalue(),
            self._expected_message("Instrumented %s %s"),
        )

    def test_does_not_write_otel_log_level_output(self):
        cases = (
            ("debug", DEBUG),
            ("info", False),
            ("debug2", False),
            ("debugger", False),
        )

        for log_level, handler_level in cases:
            with (
                self.subTest(log_level=log_level),
                patch.dict(
                    "os.environ", {"OTEL_LOG_LEVEL": log_level}, clear=True
                ),
            ):
                logger_mock = self._logger_mock()
                if handler_level:
                    handler = StreamHandler(StringIO())
                    handler.setLevel(handler_level)
                    logger_mock.handlers = [handler]

                logger = _load._OtelLogLevelLoggerAdapter(logger_mock, {})

                self.assertEqual(self._stderr_from_debug(logger), "")

                logger_mock.log.assert_called_once_with(
                    DEBUG, "Instrumented %s", "requests", extra={}
                )

    @patch.dict("os.environ", {"OTEL_LOG_LEVEL": "debug"}, clear=True)
    def test_otel_log_level_output_uses_logger_hierarchy_handlers(self):
        parent_logger = getLogger("opentelemetry.test.auto_instrumentation")
        logger = getLogger("opentelemetry.test.auto_instrumentation.loader")
        self._save_logger_state(parent_logger)
        self._save_logger_state(logger)

        parent_logger.handlers = []
        parent_logger.setLevel(DEBUG)
        parent_logger.propagate = False
        logger.handlers = []
        logger.setLevel(DEBUG)
        logger.propagate = True

        otel_log_level_logger = _load._OtelLogLevelLoggerAdapter(logger, {})
        expected_message = self._expected_message(
            "Instrumented 'requests'", logger.name
        )

        self.assertEqual(
            self._stderr_from_debug(otel_log_level_logger),
            expected_message,
        )

        null_handler = NullHandler()
        null_handler.setLevel(DEBUG)
        parent_logger.addHandler(null_handler)

        self.assertEqual(
            self._stderr_from_debug(otel_log_level_logger),
            expected_message,
        )

        stream_handler = StreamHandler(StringIO())
        stream_handler.setLevel(INFO)
        parent_logger.addHandler(stream_handler)

        self.assertEqual(
            self._stderr_from_debug(otel_log_level_logger),
            expected_message,
        )

        stream_handler.setLevel(DEBUG)

        self.assertEqual(self._stderr_from_debug(otel_log_level_logger), "")

    @patch.dict("os.environ", {"OTEL_LOG_LEVEL": "debug"}, clear=True)
    @patch(
        "opentelemetry.instrumentation.auto_instrumentation._load.get_dist_dependency_conflicts"
    )
    @patch(
        "opentelemetry.instrumentation.auto_instrumentation._load.entry_points"
    )
    def test_load_instrumentors_writes_debug_to_stderr_without_logging_handler(
        self, iter_mock, mock_dep
    ):
        logger = _load._logger.logger
        self._save_logger_state(logger)

        logger.handlers = []
        logger.setLevel(DEBUG)
        logger.propagate = False
        logger.disabled = False

        ep_mock = Mock()
        ep_mock.name = "requests"
        distro_mock = Mock()
        iter_mock.side_effect = [(), (ep_mock,), ()]
        mock_dep.return_value = None
        stderr = StringIO()

        with redirect_stderr(stderr):
            _load._load_instrumentors(distro_mock)

        self.assertEqual(
            stderr.getvalue(),
            self._expected_message("Instrumented 'requests'"),
        )
        distro_mock.load_instrumentor.assert_called_once_with(
            ep_mock, skip_dep_check=True
        )

    @patch.dict("os.environ", {"OTEL_LOG_LEVEL": "debug"}, clear=True)
    @patch(
        "opentelemetry.instrumentation.auto_instrumentation._load.get_dist_dependency_conflicts"
    )
    @patch(
        "opentelemetry.instrumentation.auto_instrumentation._load.entry_points"
    )
    def test_load_instrumentors_uses_existing_root_logging_handler(
        self, iter_mock, mock_dep
    ):
        logger = _load._logger.logger
        current = logger
        while current:
            self._save_logger_state(current)
            current.handlers = []
            current.setLevel(NOTSET)
            current.propagate = True
            current.disabled = False
            current = current.parent

        log_output = StringIO()
        handler = StreamHandler(log_output)
        handler.setLevel(DEBUG)
        root_logger = getLogger()
        root_logger.handlers = [handler]
        root_logger.setLevel(DEBUG)

        ep_mock = Mock()
        ep_mock.name = "requests"
        distro_mock = Mock()
        iter_mock.side_effect = [(), (ep_mock,), ()]
        mock_dep.return_value = None
        stderr = StringIO()

        with redirect_stderr(stderr):
            _load._load_instrumentors(distro_mock)

        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(log_output.getvalue(), "Instrumented requests\n")
        distro_mock.load_instrumentor.assert_called_once_with(
            ep_mock, skip_dep_check=True
        )
