# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
# type: ignore

from os import environ, getcwd
from os.path import abspath, dirname, pathsep
from unittest import TestCase
from unittest.mock import patch

from opentelemetry.environment_variables import OTEL_TRACES_EXPORTER
from opentelemetry.instrumentation import auto_instrumentation


class TestRun(TestCase):
    auto_instrumentation_path = dirname(abspath(auto_instrumentation.__file__))

    @classmethod
    def setUpClass(cls):
        cls.execl_patcher = patch(
            "opentelemetry.instrumentation.auto_instrumentation.execl"
        )
        cls.which_patcher = patch(
            "opentelemetry.instrumentation.auto_instrumentation.which"
        )

        cls.execl_patcher.start()
        cls.which_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls.execl_patcher.stop()
        cls.which_patcher.stop()

    @patch("sys.argv", ["instrument", ""])
    @patch.dict("os.environ", {"PYTHONPATH": ""})
    def test_empty(self):
        auto_instrumentation.run()
        self.assertEqual(
            environ["PYTHONPATH"],
            pathsep.join([self.auto_instrumentation_path, getcwd()]),
        )

    @patch("sys.argv", ["instrument", ""])
    @patch.dict("os.environ", {"PYTHONPATH": "abc"})
    def test_non_empty(self):
        auto_instrumentation.run()
        self.assertEqual(
            environ["PYTHONPATH"],
            pathsep.join([self.auto_instrumentation_path, getcwd(), "abc"]),
        )

    @patch("sys.argv", ["instrument", ""])
    @patch.dict(
        "os.environ",
        {"PYTHONPATH": pathsep.join(["abc", auto_instrumentation_path])},
    )
    def test_after_path(self):
        auto_instrumentation.run()
        self.assertEqual(
            environ["PYTHONPATH"],
            pathsep.join([self.auto_instrumentation_path, getcwd(), "abc"]),
        )

    @patch("sys.argv", ["instrument", ""])
    @patch.dict(
        "os.environ",
        {
            "PYTHONPATH": pathsep.join(
                [auto_instrumentation_path, "abc", auto_instrumentation_path]
            )
        },
    )
    def test_single_path(self):
        auto_instrumentation.run()
        self.assertEqual(
            environ["PYTHONPATH"],
            pathsep.join([self.auto_instrumentation_path, getcwd(), "abc"]),
        )


class TestExecl(TestCase):
    @patch("sys.argv", ["1", "2", "3"])
    @patch("opentelemetry.instrumentation.auto_instrumentation.which")
    @patch("opentelemetry.instrumentation.auto_instrumentation.execl")
    def test_execl(self, mock_execl, mock_which):  # pylint: disable=no-self-use
        mock_which.configure_mock(**{"return_value": "python"})

        auto_instrumentation.run()

        mock_execl.assert_called_with("python", "python", "3")


class TestArgs(TestCase):
    @patch("opentelemetry.instrumentation.auto_instrumentation.execl")
    def test_exporter(self, _):  # pylint: disable=no-self-use
        with patch("sys.argv", ["instrument", "2"]):
            auto_instrumentation.run()
            self.assertIsNone(environ.get(OTEL_TRACES_EXPORTER))

        with patch(
            "sys.argv",
            ["instrument", "--traces_exporter", "jaeger", "1", "2"],
        ):
            auto_instrumentation.run()
            self.assertEqual(environ.get(OTEL_TRACES_EXPORTER), "jaeger")
