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
from opentelemetry.instrumentation.environment_variables import (
    OTEL_PYTHON_AUTO_INSTRUMENTATION_INSTRUMENT_SUBPROCESSES,
)

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
    def test_keeps_auto_instrumentation_path_for_subprocesses(
        self, logger_mock
    ):
        for value in ("true", "TrUe", " \tTrue\n", "TRUE"):
            with self.subTest(value=value):
                with patch.dict(
                    "os.environ",
                    {
                        "PYTHONPATH": self.auto_instrumentation_path
                        + pathsep
                        + "foo",
                        OTEL_PYTHON_AUTO_INSTRUMENTATION_INSTRUMENT_SUBPROCESSES: value,
                    },
                ):
                    auto_instrumentation.initialize()
                    self.assertEqual(
                        environ["PYTHONPATH"],
                        self.auto_instrumentation_path + pathsep + "foo",
                    )
                    logger_mock.exception.assert_not_called()

    @patch.dict(
        "os.environ",
        {
            "PYTHONPATH": auto_instrumentation_path + pathsep + "foo",
            OTEL_PYTHON_AUTO_INSTRUMENTATION_INSTRUMENT_SUBPROCESSES: "false",
        },
    )
    @patch("opentelemetry.instrumentation.auto_instrumentation._logger")
    def test_clears_auto_instrumentation_path_when_subprocesses_false(
        self, logger_mock
    ):
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
        load_distro_mock.side_effect = ValueError("inner exception")
        with self.assertRaises(ValueError) as em:
            auto_instrumentation.initialize(swallow_exceptions=False)
            logger_mock.exception.assert_called_once_with(
                "Failed to auto initialize OpenTelemetry"
            )

        self.assertEqual("inner exception", str(em.exception))

    @patch.dict(
        "os.environ",
        {
            "OTEL_PYTHON_AUTO_INSTRUMENTATION_EXPERIMENTAL_GEVENT_PATCH": "patch_foo"
        },
    )
    @patch("opentelemetry.instrumentation.auto_instrumentation._logger")
    def test_handles_invalid_gevent_monkeypatch(self, logger_mock):
        # pylint:disable=no-self-use
        auto_instrumentation.initialize()
        logger_mock.error.assert_called_once_with(
            "%s value must be `patch_all`",
            "OTEL_PYTHON_AUTO_INSTRUMENTATION_EXPERIMENTAL_GEVENT_PATCH",
        )

    @patch.dict(
        "os.environ",
        {
            "OTEL_PYTHON_AUTO_INSTRUMENTATION_EXPERIMENTAL_GEVENT_PATCH": "patch_all"
        },
    )
    @patch("opentelemetry.instrumentation.auto_instrumentation._logger")
    def test_handles_patch_all_gevent_monkeypatch(self, logger_mock):
        # pylint:disable=no-self-use
        auto_instrumentation.initialize()
        logger_mock.error.assert_not_called()
