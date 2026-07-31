# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
# type: ignore

import subprocess
import sys
from os import environ
from os.path import abspath, dirname, pathsep
from unittest import TestCase
from unittest.mock import MagicMock, patch

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
    def test_restores_auto_instrumentation_path_after_init(self, logger_mock):
        auto_instrumentation.initialize()
        paths = environ["PYTHONPATH"].split(pathsep)
        self.assertIn(self.auto_instrumentation_path, paths)
        self.assertIn("foo", paths)
        logger_mock.exception.assert_not_called()

    @patch.dict(
        "os.environ",
        {"PYTHONPATH": auto_instrumentation_path + pathsep + "foo"},
    )
    @patch("opentelemetry.instrumentation.auto_instrumentation._logger")
    @patch("opentelemetry.instrumentation.auto_instrumentation._load_distro")
    def test_preserves_pythonpath_changes_during_init(
        self, load_distro_mock, _logger_mock
    ):
        def modify_pythonpath(*_):
            environ["PYTHONPATH"] = (
                environ.get("PYTHONPATH", "") + pathsep + "added_during_init"
            )
            distro = MagicMock()
            distro.configure.return_value = None
            return distro

        load_distro_mock.side_effect = modify_pythonpath
        auto_instrumentation.initialize()
        paths = environ["PYTHONPATH"].split(pathsep)
        self.assertIn(self.auto_instrumentation_path, paths)
        self.assertIn("added_during_init", paths)

    @patch.dict(
        "os.environ",
        {"PYTHONPATH": auto_instrumentation_path + pathsep + "foo"},
    )
    @patch("opentelemetry.instrumentation.auto_instrumentation._logger")
    @patch("opentelemetry.instrumentation.auto_instrumentation._load_distro")
    def test_subprocess_sees_pythonpath_changes(
        self, load_distro_mock, _logger_mock
    ):
        during_init_paths: list[str] | None = None

        def capture_pythonpath_in_subprocess(*_):
            nonlocal during_init_paths
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import os; print(os.environ.get('PYTHONPATH', ''))",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            raw = result.stdout.strip()
            during_init_paths = raw.split(pathsep) if raw else []
            distro = MagicMock()
            distro.configure.return_value = None
            return distro

        load_distro_mock.side_effect = capture_pythonpath_in_subprocess
        auto_instrumentation.initialize()

        self.assertIsNotNone(during_init_paths)
        self.assertNotIn(self.auto_instrumentation_path, during_init_paths)

        result_after = subprocess.run(
            [
                sys.executable,
                "-c",
                "import os; print(os.environ.get('PYTHONPATH', ''))",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        raw_after = result_after.stdout.strip()
        after_init_paths = raw_after.split(pathsep) if raw_after else []
        self.assertIn(self.auto_instrumentation_path, after_init_paths)

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
