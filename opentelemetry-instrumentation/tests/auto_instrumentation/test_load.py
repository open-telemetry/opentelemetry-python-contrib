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
# type: ignore

from unittest import TestCase
from unittest.mock import Mock, call, patch

from opentelemetry.instrumentation.auto_instrumentation import _load
from opentelemetry.instrumentation.dependencies import (
    DependencyConflict,
    DependencyConflictError,
)
from opentelemetry.instrumentation.environment_variables import (
    OTEL_PYTHON_CONFIGURATOR,
    OTEL_PYTHON_DISABLED_INSTRUMENTATIONS,
    OTEL_PYTHON_DISTRO,
)
from opentelemetry.instrumentation.version import __version__


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
        "opentelemetry.instrumentation.auto_instrumentation._load.entry_points"
    )
    def test_load_instrumentors(self, iter_mock):
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
        _load._load_instrumentors(distro_mock)
        # All opentelemetry_pre_instrument entry points should be loaded
        pre_mock1.assert_called_once()
        pre_mock2.assert_called_once()
        self.assertEqual(iter_mock.call_count, 3)
        # Only non-disabled instrumentations should be loaded
        distro_mock.load_instrumentor.assert_has_calls(
            [
                call(ep_mock2, raise_exception_on_conflict=True),
                call(ep_mock4, raise_exception_on_conflict=True),
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
    @patch("opentelemetry.instrumentation.auto_instrumentation._load._logger")
    @patch(
        "opentelemetry.instrumentation.auto_instrumentation._load.entry_points"
    )
    def test_load_instrumentors_dep_conflict(self, iter_mock, mock_logger):  # pylint: disable=no-self-use
        ep_mock1 = Mock()
        ep_mock1.name = "instr1"

        ep_mock2 = Mock()
        ep_mock2.name = "instr2"

        ep_mock3 = Mock()
        ep_mock3.name = "instr3"

        ep_mock4 = Mock()
        ep_mock4.name = "instr4"

        dependency_conflict = DependencyConflict("1.2.3", None)

        distro_mock = Mock()
        distro_mock.load_instrumentor.side_effect = [
            None,
            DependencyConflictError(dependency_conflict),
        ]

        # If a dependency conflict is raised, that instrumentation should not be loaded, but others still should.
        # In this case, ep_mock4 will fail to load and ep_mock2 will succeed. (ep_mock1 and ep_mock3 are disabled)
        iter_mock.return_value = (ep_mock1, ep_mock2, ep_mock3, ep_mock4)
        _load._load_instrumentors(distro_mock)
        distro_mock.load_instrumentor.assert_has_calls(
            [
                call(ep_mock2, raise_exception_on_conflict=True),
                call(ep_mock4, raise_exception_on_conflict=True),
            ]
        )
        assert distro_mock.load_instrumentor.call_count == 2
        mock_logger.debug.assert_has_calls(
            [
                self._instrumentation_failed_to_load_call(
                    ep_mock4.name, dependency_conflict
                )
            ]
        )

    @patch("opentelemetry.instrumentation.auto_instrumentation._load._logger")
    @patch(
        "opentelemetry.instrumentation.auto_instrumentation._load.entry_points"
    )
    def test_load_instrumentors_import_error_does_not_stop_everything(
        self, iter_mock, mock_logger
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

        _load._load_instrumentors(distro_mock)

        distro_mock.load_instrumentor.assert_has_calls(
            [
                call(ep_mock1, raise_exception_on_conflict=True),
                call(ep_mock2, raise_exception_on_conflict=True),
            ]
        )
        self.assertEqual(distro_mock.load_instrumentor.call_count, 2)
        mock_logger.exception.assert_any_call(
            "Importing of %s failed, skipping it",
            ep_mock1.name,
        )

        mock_logger.debug.assert_any_call("Instrumented %s", ep_mock2.name)

    @patch(
        "opentelemetry.instrumentation.auto_instrumentation._load.entry_points"
    )
    def test_load_instrumentors_raises_exception(self, iter_mock):
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

        with self.assertRaises(ValueError):
            _load._load_instrumentors(distro_mock)

        distro_mock.load_instrumentor.assert_has_calls(
            [
                call(ep_mock1, raise_exception_on_conflict=True),
            ]
        )
        self.assertEqual(distro_mock.load_instrumentor.call_count, 1)

    @patch("opentelemetry.instrumentation.auto_instrumentation._load._logger")
    @patch(
        "opentelemetry.instrumentation.auto_instrumentation._load.entry_points"
    )
    def test_load_instrumentors_module_not_found_error(
        self, iter_mock, mock_logger
    ):
        ep_mock1 = Mock()
        ep_mock1.name = "instr1"

        ep_mock2 = Mock()
        ep_mock2.name = "instr2"

        distro_mock = Mock()

        distro_mock.load_instrumentor.side_effect = [
            ModuleNotFoundError("No module named 'fake_module'"),
            None,
        ]

        iter_mock.side_effect = [(), (ep_mock1, ep_mock2), ()]

        _load._load_instrumentors(distro_mock)

        distro_mock.load_instrumentor.assert_has_calls(
            [
                call(ep_mock1, raise_exception_on_conflict=True),
                call(ep_mock2, raise_exception_on_conflict=True),
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
