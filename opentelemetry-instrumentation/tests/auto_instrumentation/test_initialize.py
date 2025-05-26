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

from os import environ
from os.path import abspath, dirname, pathsep
from unittest import TestCase
from unittest.mock import patch

from opentelemetry.instrumentation import auto_instrumentation

# TODO: convert to assertNoLogs instead of mocking logger when 3.10 is baseline


class TestInitialize(TestCase):
    auto_instrumentation_path = dirname(abspath(auto_instrumentation.__file__))

    @patch.dict("os.environ", {}, clear=True)
    @patch("opentelemetry.instrumentation.auto_instrumentation._logger")
    def test_handles_pythonpath_not_set(self, logger_mock):
        auto_instrumentation.initialize()
        self.assertNotIn("PYTHONPATH", environ)
        logger_mock.exception.assert_not_called()

    @patch.dict("os.environ", {"PYTHONPATH": "."})
    @patch("opentelemetry.instrumentation.auto_instrumentation._logger")
    def test_handles_pythonpath_set(self, logger_mock):
        auto_instrumentation.initialize()
        self.assertEqual(environ["PYTHONPATH"], ".")
        logger_mock.exception.assert_not_called()

    @patch.dict(
        "os.environ",
        {"PYTHONPATH": auto_instrumentation_path + pathsep + "foo"},
    )
    @patch("opentelemetry.instrumentation.auto_instrumentation._logger")
    def test_clears_auto_instrumentation_path(self, logger_mock):
        auto_instrumentation.initialize()
        self.assertEqual(environ["PYTHONPATH"], "foo")
        logger_mock.exception.assert_not_called()

    @patch("opentelemetry.instrumentation.auto_instrumentation._logger")
    @patch("opentelemetry.instrumentation.auto_instrumentation._load_distro")
    def test_handles_exceptions(self, load_distro_mock, logger_mock):
        # pylint:disable=no-self-use
        load_distro_mock.side_effect = ValueError
        auto_instrumentation.initialize()
        logger_mock.exception.assert_called_once_with(
            "Failed to auto initialize OpenTelemetry"
        )

    @patch("opentelemetry.instrumentation.auto_instrumentation._logger")
    @patch("opentelemetry.instrumentation.auto_instrumentation._load_distro")
    def test_reraises_exceptions(self, load_distro_mock, logger_mock):
        # pylint:disable=no-self-use
        load_distro_mock.side_effect = ValueError
        with self.assertRaises(ValueError) as em:
            auto_instrumentation.initialize(swallow_exceptions=False)
            logger_mock.exception.assert_called_once_with(
                "Failed to auto initialize OpenTelemetry"
            )

        self.assertEqual(
            "Failed to auto initialize OpenTelemetry", str(em.exception)
        )
