# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
# type: ignore

from io import StringIO
from random import sample
from unittest import TestCase
from unittest.mock import call, patch

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

    @patch("sys.argv", ["bootstrap", "-a", "requirements", "-e", "wsgi"])
    def test_can_exclude_library_and_instrumentation(self):
        fake_libraries = [
            {"library": "wsgi", "instrumentation": "opentelemetry-instrumentation-wsgi"},
            {"library": "flask", "instrumentation": "opentelemetry-instrumentation-flask"},
        ]

        fake_default_instrumentations = [
            "opentelemetry-instrumentation-wsgi",
            "opentelemetry-instrumentation-fastapi",
        ]

        def fake_is_installed(lib):
            return lib in {"flask", "fastapi"}

        with (
            patch("opentelemetry.instrumentation.bootstrap.gen_libraries", fake_libraries),
            patch(
                "opentelemetry.instrumentation.bootstrap.gen_default_instrumentations", fake_default_instrumentations
            ),
            patch(
                "opentelemetry.instrumentation.bootstrap._is_installed",
                side_effect=fake_is_installed,
            ),
            patch("sys.stdout", new=StringIO()) as fake_out,
        ):
            bootstrap.run()

        self.assertEqual(
            fake_out.getvalue().strip(), "opentelemetry-instrumentation-fastapi\nopentelemetry-instrumentation-flask"
        )

    @patch("sys.argv", ["bootstrap", "-a", "requirements", "-e", "does-not-exist"])
    def test_run_with_unmatched_exclude_is_noop(self):
        libraries = [
            {"library": "flask", "instrumentation": "opentelemetry-instrumentation-flask"},
        ]
        default_instrumentations = ["opentelemetry-instrumentation-fastapi"]

        def fake_is_installed(lib):
            return lib in {"flask", "fastapi"}

        with (
            patch("opentelemetry.instrumentation.bootstrap.gen_libraries", libraries),
            patch("opentelemetry.instrumentation.bootstrap.gen_default_instrumentations", default_instrumentations),
            patch(
                "opentelemetry.instrumentation.bootstrap._is_installed",
                side_effect=fake_is_installed,
            ),
            patch("sys.stdout", new=StringIO()) as fake_out,
        ):
            bootstrap.run()

        self.assertEqual(
            fake_out.getvalue().strip(), "opentelemetry-instrumentation-fastapi\nopentelemetry-instrumentation-flask"
        )

    @patch("sys.argv", ["bootstrap", "-a", "requirements", "-e", "system_metrics"])
    def test_exclude_normalizes(self):
        default_instrumentations = ["opentelemetry-instrumentation-system-metrics"]

        def fake_is_installed(lib):
            return lib in {"system-metrics"}

        with (
            patch(
                "opentelemetry.instrumentation.bootstrap.gen_default_instrumentations",
                default_instrumentations,
            ),
            patch(
                "opentelemetry.instrumentation.bootstrap._is_installed",
                side_effect=fake_is_installed,
            ),
            patch("sys.stdout", new=StringIO()) as fake_out,
        ):
            bootstrap.run()

        self.assertEqual(fake_out.getvalue().strip(), "")

    @patch("sys.argv", ["bootstrap", "-a", "requirements", "-e", "urllib"])
    def test_exclude_does_not_match_similar_package_names(self):
        libraries = [
            {"library": "urllib", "instrumentation": "opentelemetry-instrumentation-urllib"},
            {"library": "urllib3", "instrumentation": "opentelemetry-instrumentation-urllib3"},
        ]

        def fake_is_installed(lib):
            return lib in {"urllib", "urllib3"}

        with (
            patch("opentelemetry.instrumentation.bootstrap.gen_libraries", libraries),
            patch("opentelemetry.instrumentation.bootstrap.gen_default_instrumentations", []),
            patch(
                "opentelemetry.instrumentation.bootstrap._is_installed",
                side_effect=fake_is_installed,
            ),
            patch("sys.stdout", new=StringIO()) as fake_out,
        ):
            bootstrap.run()

        self.assertEqual(
            fake_out.getvalue().strip(),
            "opentelemetry-instrumentation-urllib3",
        )
