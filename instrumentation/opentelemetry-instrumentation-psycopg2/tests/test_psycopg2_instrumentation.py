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
from importlib.metadata import PackageNotFoundError
from unittest import TestCase
from unittest.mock import Mock, call, patch

import psycopg2

from opentelemetry.instrumentation.auto_instrumentation._load import (
    _load_instrumentors,
)
from opentelemetry.instrumentation.psycopg2 import (
    DatabaseApiIntegration,
    Psycopg2Instrumentor,
)
from opentelemetry.instrumentation.psycopg2.package import (
    _instruments_psycopg2,
    _instruments_psycopg2_binary,
)
from opentelemetry.instrumentation.psycopg2.version import __version__
from opentelemetry.test.test_base import TestBase


class TestPsycopg2InstrumentationDependencies(TestCase):
    """
    The psycopg2 instrumentation is special in that it can instrument
    multiple packages. (psycopg2 and psycopg2-binary)
    The tests below are to verify that the correct package is instrumented
    depending on which package is installed.
    Including the cases where both are installed and neither is installed.
    These tests were added after we found a bug where the auto instrumentation
    path attempted to use a different dependency check than the manual
    instrumentation path. This caused the auto instrumentation to fail.

    """

    @patch("opentelemetry.instrumentation.psycopg2.distribution")
    def test_instrumentation_dependencies_psycopg2_installed(
        self, mock_distribution
    ) -> None:
        instrumentation = Psycopg2Instrumentor()

        def _distribution(name):
            if name == "psycopg2":
                return None
            raise PackageNotFoundError

        mock_distribution.side_effect = _distribution
        package_to_instrument = instrumentation.instrumentation_dependencies()

        self.assertEqual(mock_distribution.call_count, 1)
        self.assertEqual(
            mock_distribution.mock_calls,
            [
                call("psycopg2"),
            ],
        )
        self.assertEqual(package_to_instrument, (_instruments_psycopg2,))

    @patch("opentelemetry.instrumentation.psycopg2.distribution")
    def test_instrumentation_dependencies_psycopg2_binary_installed(
        self, mock_distribution
    ) -> None:
        instrumentation = Psycopg2Instrumentor()

        def _distribution(name):
            if name == "psycopg2-binary":
                return None
            raise PackageNotFoundError

        mock_distribution.side_effect = _distribution
        package_to_instrument = instrumentation.instrumentation_dependencies()

        self.assertEqual(mock_distribution.call_count, 2)
        self.assertEqual(
            mock_distribution.mock_calls,
            [
                call("psycopg2"),
                call("psycopg2-binary"),
            ],
        )
        self.assertEqual(
            package_to_instrument, (_instruments_psycopg2_binary,)
        )

    @patch("opentelemetry.instrumentation.psycopg2.distribution")
    def test_instrumentation_dependencies_both_installed(
        self, mock_distribution
    ) -> None:
        instrumentation = Psycopg2Instrumentor()

        def _distribution(name):
            # The function returns None here for all names
            # to simulate both packages being installed
            return None

        mock_distribution.side_effect = _distribution
        package_to_instrument = instrumentation.instrumentation_dependencies()

        self.assertEqual(mock_distribution.call_count, 1)
        self.assertEqual(mock_distribution.mock_calls, [call("psycopg2")])
        self.assertEqual(package_to_instrument, (_instruments_psycopg2,))

    @patch("opentelemetry.instrumentation.psycopg2.distribution")
    def test_instrumentation_dependencies_none_installed(
        self, mock_distribution
    ) -> None:
        instrumentation = Psycopg2Instrumentor()

        def _distribution(name):
            # Function raises PackageNotFoundError
            # if name is not in the list. We will
            # raise it for both names to simulate
            # neither being installed
            raise PackageNotFoundError

        mock_distribution.side_effect = _distribution
        package_to_instrument = instrumentation.instrumentation_dependencies()

        self.assertEqual(mock_distribution.call_count, 2)
        self.assertEqual(
            mock_distribution.mock_calls,
            [
                call("psycopg2"),
                call("psycopg2-binary"),
            ],
        )
        self.assertEqual(
            package_to_instrument,
            (
                _instruments_psycopg2,
                _instruments_psycopg2_binary,
            ),
        )

    # This test is to verify that the auto instrumentation path
    # will auto instrument psycopg2 or psycopg2-binary is installed.
    # Note there is only one test here but it is run twice in tox
    # once with the psycopg2 package installed and once with
    # psycopg2-binary installed.
    @patch(
        "opentelemetry.instrumentation.auto_instrumentation._load.get_dist_dependency_conflicts"
    )
    @patch("opentelemetry.instrumentation.auto_instrumentation._load._logger")
    def test_instruments_with_psycopg2_installed(self, mock_logger, mock_dep):
        def _instrumentation_loaded_successfully_call():
            return call("Instrumented %s", "psycopg2")

        mock_distro = Mock()
        mock_dep.return_value = None
        mock_distro.load_instrumentor.return_value = None
        _load_instrumentors(mock_distro)
        self.assertEqual(len(mock_distro.load_instrumentor.call_args_list), 1)
        (ep,) = mock_distro.load_instrumentor.call_args.args
        self.assertEqual(ep.name, "psycopg2")
        mock_logger.debug.assert_has_calls(
            [_instrumentation_loaded_successfully_call()]
        )


@patch("opentelemetry.instrumentation.psycopg2.dbapi")
class TestPsycopg2InstrumentorParameters(TestBase):
    def tearDown(self):
        super().tearDown()
        with self.disable_logging():
            Psycopg2Instrumentor().uninstrument()

    def test_instrument_defaults(self, mock_dbapi):
        Psycopg2Instrumentor().instrument()

        mock_dbapi.wrap_connect.assert_called_once_with(
            "opentelemetry.instrumentation.psycopg2",
            psycopg2,
            "connect",
            "postgresql",
            {
                "database": "info.dbname",
                "port": "info.port",
                "host": "info.host",
                "user": "info.user",
            },
            version=__version__,
            tracer_provider=None,
            db_api_integration_factory=DatabaseApiIntegration,
            enable_commenter=False,
            commenter_options={},
            enable_attribute_commenter=False,
            capture_parameters=False,
        )

    def test_instrument_capture_parameters(self, mock_dbapi):
        Psycopg2Instrumentor().instrument(capture_parameters=True)

        self.assertTrue(
            mock_dbapi.wrap_connect.call_args.kwargs["capture_parameters"]
        )
