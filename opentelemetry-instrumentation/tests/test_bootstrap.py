# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
# type: ignore

from io import StringIO
from random import sample
from unittest import TestCase
from unittest.mock import call, patch

from packaging.version import InvalidVersion

from opentelemetry.instrumentation import bootstrap
from opentelemetry.instrumentation.bootstrap_gen import (
    default_instrumentations,
    libraries,
)


def sample_packages(packages, rate):
    return sample(
        list(packages),
        int(len(packages) * rate),
    )


class TestBootstrap(TestCase):
    installed_libraries = {}
    installed_instrumentations = {}

    @classmethod
    def setUpClass(cls):
        cls.installed_libraries = sample_packages([lib["instrumentation"] for lib in libraries], 0.6)

        # treat 50% of sampled packages as pre-installed
        cls.installed_instrumentations = sample_packages(cls.installed_libraries, 0.5)

        cls.pkg_patcher = patch(
            "opentelemetry.instrumentation.bootstrap._find_installed_libraries",
            return_value=cls.installed_libraries,
        )

        cls.pip_install_patcher = patch(
            "opentelemetry.instrumentation.bootstrap._sys_pip_install",
        )
        cls.pip_check_patcher = patch(
            "opentelemetry.instrumentation.bootstrap._pip_check",
        )

    def setUp(self):
        super().setUp()
        self.mock_pip_check = self.pip_check_patcher.start()
        self.mock_pip_install = self.pip_install_patcher.start()

    def tearDown(self):
        super().tearDown()
        self.pip_check_patcher.stop()
        self.pip_install_patcher.stop()

    @patch("sys.argv", ["bootstrap", "-a", "pipenv"])
    def test_run_unknown_cmd(self):
        with self.assertRaises(SystemExit):
            bootstrap.run()

    @patch("sys.argv", ["bootstrap", "-a", "requirements"])
    def test_run_cmd_print(self):
        self.pkg_patcher.start()
        with patch("sys.stdout", new=StringIO()) as fake_out:
            bootstrap.run()
            self.assertEqual(
                fake_out.getvalue(),
                "\n".join(self.installed_libraries) + "\n",
            )
        self.pkg_patcher.stop()

    @patch("sys.argv", ["bootstrap", "-a", "install"])
    def test_run_cmd_install(self):
        self.pkg_patcher.start()
        bootstrap.run()
        self.mock_pip_install.assert_has_calls(
            [call(i) for i in self.installed_libraries],
            any_order=True,
        )
        self.mock_pip_check.assert_called_once()
        self.pkg_patcher.stop()

    @patch("sys.argv", ["bootstrap", "-a", "install"])
    def test_can_override_available_libraries(self):
        bootstrap.run(libraries=[])
        self.mock_pip_install.assert_has_calls(
            [call(i) for i in default_instrumentations],
            any_order=True,
        )
        self.mock_pip_check.assert_called_once()

    @patch("sys.argv", ["bootstrap", "-a", "install"])
    def test_can_override_available_default_instrumentations(self):
        with patch(
            "opentelemetry.instrumentation.bootstrap._is_installed",
            return_value=True,
        ):
            bootstrap.run(default_instrumentations=[])
        self.mock_pip_install.assert_has_calls(
            [call(i) for i in self.installed_libraries],
            any_order=True,
        )
        self.mock_pip_check.assert_called_once()


class TestIsInstalled(TestCase):
    @patch("opentelemetry.instrumentation.bootstrap.version", return_value="1.5.0")
    def test_version_in_range(self, mock_version):
        with self.assertNoLogs(bootstrap.logger, level="WARNING"):
            self.assertTrue(bootstrap._is_installed("foo >= 1.0, < 2.0"))
        mock_version.assert_called_once_with("foo")

    @patch("opentelemetry.instrumentation.bootstrap.version", return_value="2.1.0")
    def test_version_out_of_range(self, _):
        with self.assertLogs(bootstrap.logger, level="WARNING") as logs:
            self.assertFalse(bootstrap._is_installed("foo >= 1.0, < 2.0"))
        self.assertIn("version 2.1.0 is installed", logs.output[0])

    # packaging 22-25 raise InvalidVersion for non-PEP 440 versions
    @patch("opentelemetry.instrumentation.bootstrap.version", return_value="1.0-SNAPSHOT")
    @patch("packaging.specifiers.SpecifierSet.contains", side_effect=InvalidVersion)
    def test_invalid_version(self, mock_contains, _):
        with self.assertLogs(bootstrap.logger, level="WARNING") as logs:
            self.assertFalse(bootstrap._is_installed("foo >= 1.0, < 2.0"))
        mock_contains.assert_called_once()
        self.assertIn("version 1.0-SNAPSHOT is installed", logs.output[0])

    # version() returns None for a dist-info without a Version field
    @patch("opentelemetry.instrumentation.bootstrap.version", return_value=None)
    def test_missing_version(self, _):
        with self.assertLogs(bootstrap.logger, level="WARNING") as logs:
            self.assertFalse(bootstrap._is_installed("foo >= 1.0, < 2.0"))
        self.assertIn("version None is installed", logs.output[0])
