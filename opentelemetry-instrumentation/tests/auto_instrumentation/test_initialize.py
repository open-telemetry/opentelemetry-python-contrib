# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
# type: ignore

import logging
import subprocess
import sys
from os import environ
from os.path import abspath, dirname, pathsep
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import MagicMock, patch

from opentelemetry.instrumentation import auto_instrumentation
from opentelemetry.instrumentation.distro import BaseDistro

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
    def test_preserves_pythonpath_changes_during_init(self, load_distro_mock, _logger_mock):
        def modify_pythonpath(*_):
            environ["PYTHONPATH"] = environ.get("PYTHONPATH", "") + pathsep + "added_during_init"
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
    def test_subprocess_sees_pythonpath_changes(self, load_distro_mock, _logger_mock):
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
        logger_mock.exception.assert_called_once_with("Failed to auto initialize OpenTelemetry")
        logger_mock.info.assert_not_called()

    @patch("opentelemetry.instrumentation.auto_instrumentation._logger")
    @patch("opentelemetry.instrumentation.auto_instrumentation._load_distro")
    def test_reraises_exceptions(self, load_distro_mock, logger_mock):
        # pylint:disable=no-self-use
        load_distro_mock.side_effect = ValueError("inner exception")
        with self.assertRaises(ValueError) as em:
            auto_instrumentation.initialize(swallow_exceptions=False)
            logger_mock.exception.assert_called_once_with("Failed to auto initialize OpenTelemetry")

        self.assertEqual("inner exception", str(em.exception))
        logger_mock.info.assert_not_called()

    @patch.dict(
        "os.environ",
        {"OTEL_PYTHON_AUTO_INSTRUMENTATION_EXPERIMENTAL_GEVENT_PATCH": "patch_foo"},
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
        {"OTEL_PYTHON_AUTO_INSTRUMENTATION_EXPERIMENTAL_GEVENT_PATCH": "patch_all"},
    )
    @patch("opentelemetry.instrumentation.auto_instrumentation._logger")
    def test_handles_patch_all_gevent_monkeypatch(self, logger_mock):
        # pylint:disable=no-self-use
        auto_instrumentation.initialize()
        logger_mock.error.assert_not_called()


class _FakeDistro(BaseDistro):
    def _configure(self, **_kwargs: object) -> None:
        handler = logging.StreamHandler()
        handler.setLevel(logging.WARNING)
        logging.getLogger().addHandler(handler)


def _fake_post_instrumentation() -> None:
    print("POST_INSTRUMENTATION_COMPLETED", file=sys.stderr)


def _fake_failing_post_instrumentation() -> None:
    raise RuntimeError("instrumentor startup failed")


class TestStartupConfirmation(TestCase):
    @staticmethod
    def _run_initialization(
        post_instrumentation_hook: str, application_log_level: str | None = None
    ) -> subprocess.CompletedProcess[str]:
        with TemporaryDirectory() as directory:
            distribution = Path(directory) / "startup_confirmation_test-1.0.dist-info"
            distribution.mkdir()
            (distribution / "METADATA").write_text(
                "Metadata-Version: 2.1\nName: startup-confirmation-test\nVersion: 1.0\n",
                encoding="utf-8",
            )
            (distribution / "entry_points.txt").write_text(
                "[opentelemetry_distro]\n"
                "startup-confirmation-test = test_initialize:_FakeDistro\n"
                "[opentelemetry_post_instrument]\n"
                f"startup_confirmation = test_initialize:{post_instrumentation_hook}\n",
                encoding="utf-8",
            )
            env = {
                key: value
                for key, value in environ.items()
                if not key.startswith("OTEL_") and key not in ("PYTHONPATH", "PYTHONHOME")
            }
            env.update(
                {
                    "PYTHONPATH": pathsep.join((directory, str(Path(__file__).parent))),
                    "OTEL_PYTHON_DISTRO": "startup-confirmation-test",
                    "OTEL_PYTHON_CONFIGURATOR": "startup-confirmation-test",
                    "OTEL_PYTHON_DISABLED_INSTRUMENTATIONS": "*",
                }
            )
            code = "import logging; from opentelemetry.instrumentation.auto_instrumentation import initialize; "
            if application_log_level is not None:
                code += (
                    f"logging.basicConfig(level=logging.{application_log_level}, "
                    "format='APP:%(levelname)s:%(name)s:%(message)s'); "
                )
            code += "initialize()"
            return subprocess.run(
                [
                    sys.executable,
                    "-c",
                    code,
                ],
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )

    def test_reports_completion_after_instrumentors_load(self) -> None:
        result = self._run_initialization(post_instrumentation_hook="_fake_post_instrumentation")
        message = "OpenTelemetry automatic instrumentation started successfully"
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr.count(message), 1, result.stderr)
        self.assertEqual(
            result.stderr.splitlines()[-2:],
            [
                "POST_INSTRUMENTATION_COMPLETED",
                message,
            ],
        )

    def test_does_not_report_completion_when_instrumentation_fails(self) -> None:
        result = self._run_initialization(post_instrumentation_hook="_fake_failing_post_instrumentation")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Failed to auto initialize OpenTelemetry", result.stderr)
        self.assertIn("instrumentor startup failed", result.stderr)
        self.assertNotIn("OpenTelemetry automatic instrumentation started successfully", result.stderr)

    def test_application_logging_configured_after_import_controls_startup_output(self) -> None:
        message = "OpenTelemetry automatic instrumentation started successfully"
        for level, expected_count in (("DEBUG", 1), ("WARNING", 0)):
            with self.subTest(level=level):
                result = self._run_initialization(
                    post_instrumentation_hook="_fake_post_instrumentation",
                    application_log_level=level,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr.count(message), expected_count, result.stderr)
                self.assertNotIn("\n" + message, result.stderr)
                if level == "DEBUG":
                    logger_name = "opentelemetry.instrumentation.auto_instrumentation"
                    self.assertIn(f"APP:INFO:{logger_name}:" + message, result.stderr)
                    self.assertIn(
                        f"APP:DEBUG:{logger_name}:Loaded OpenTelemetry distribution: test_initialize._FakeDistro",
                        result.stderr,
                    )
