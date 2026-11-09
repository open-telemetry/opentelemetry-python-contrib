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

    @patch(
        "sys.argv",
        ["bootstrap", "-a", "requirements", "-e", "opentelemetry-instrumentation-aiohttp-client"],
    )
    def test_can_exclude_instrumentation_package(self):
        aiohttp_instrumentations = [
            library["instrumentation"] for library in libraries if library["library"].startswith("aiohttp ")
        ]
        aiohttp_client = next(
            instrumentation
            for instrumentation in aiohttp_instrumentations
            if instrumentation.startswith("opentelemetry-instrumentation-aiohttp-client")
        )
        aiohttp_server = next(
            instrumentation
            for instrumentation in aiohttp_instrumentations
            if instrumentation.startswith("opentelemetry-instrumentation-aiohttp-server")
        )

        with (
            patch(
                "opentelemetry.instrumentation.bootstrap._is_installed",
                side_effect=lambda requirement: requirement.startswith("aiohttp "),
            ),
            patch("sys.stdout", new=StringIO()) as fake_out,
        ):
            bootstrap.run()

        self.assertEqual(
            fake_out.getvalue().strip(),
            "\n".join([*default_instrumentations, aiohttp_server]),
        )
        self.assertNotIn(aiohttp_client, fake_out.getvalue())

    @patch(
        "sys.argv",
        ["bootstrap", "-a", "requirements", "-e", "aiohttp"],
    )
    def test_exclude_does_not_match_dependency_name(self):
        aiohttp_instrumentations = [
            library["instrumentation"] for library in libraries if library["library"].startswith("aiohttp ")
        ]

        with (
            patch(
                "opentelemetry.instrumentation.bootstrap._is_installed",
                side_effect=lambda requirement: requirement.startswith("aiohttp "),
            ),
            patch("sys.stdout", new=StringIO()) as fake_out,
        ):
            bootstrap.run()

        self.assertEqual(
            fake_out.getvalue().strip(),
            "\n".join([*default_instrumentations, *aiohttp_instrumentations]),
        )

    @patch(
        "sys.argv",
        ["bootstrap", "-a", "requirements", "-e", "opentelemetry-instrumentation-logging"],
    )
    def test_can_exclude_default_instrumentation_package(self):
        logging_instrumentation = next(
            instrumentation
            for instrumentation in default_instrumentations
            if instrumentation.startswith("opentelemetry-instrumentation-logging")
        )

        with (
            patch("opentelemetry.instrumentation.bootstrap._is_installed", return_value=False),
            patch("sys.stdout", new=StringIO()) as fake_out,
        ):
            bootstrap.run()

        self.assertEqual(
            fake_out.getvalue().strip(),
            "\n".join(
                instrumentation
                for instrumentation in default_instrumentations
                if instrumentation != logging_instrumentation
            ),
        )

    @patch("sys.argv", ["bootstrap", "-a", "requirements", "-e", "does-not-exist"])
    def test_run_with_unmatched_exclude_is_noop(self):
        with (
            patch("opentelemetry.instrumentation.bootstrap._is_installed", return_value=False),
            patch("sys.stdout", new=StringIO()) as fake_out,
        ):
            bootstrap.run()

        self.assertEqual(fake_out.getvalue().strip(), "\n".join(default_instrumentations))

    @patch("sys.argv", ["bootstrap", "-a", "requirements", "-e", "opentelemetry-instrumentation-urllib"])
    def test_exclude_does_not_match_similar_instrumentation_suffixes(self):
        fake_libraries = [
            {"library": "first-library", "instrumentation": "opentelemetry-instrumentation-urllib"},
            {"library": "second-library", "instrumentation": "opentelemetry-instrumentation-urllib3"},
        ]

        def fake_is_installed(lib):
            return lib in {"first-library", "second-library"}

        with (
            patch("opentelemetry.instrumentation.bootstrap.gen_libraries", fake_libraries),
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
