# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# pylint: disable=protected-access

from unittest.mock import Mock, patch

import pytest
from packaging.requirements import Requirement

from opentelemetry.instrumentation.dependencies import (
    DependencyConflict,
    get_dependency_conflicts,
    get_dist_dependency_conflicts,
)
from opentelemetry.test.test_base import TestBase
from opentelemetry.util._importlib_metadata import (
    Distribution,
    PackageNotFoundError,
)


class TestDependencyConflicts(TestBase):
    def test_get_dependency_conflicts_empty(self):
        self.assertIsNone(get_dependency_conflicts([]))

    def test_get_dependency_conflicts_no_conflict_requirement(self):
        req = Requirement("pytest")
        self.assertIsNone(get_dependency_conflicts([req]))

    def test_get_dependency_conflicts_no_conflict(self):
        self.assertIsNone(get_dependency_conflicts(["pytest"]))

    def test_get_dependency_conflicts_not_installed_requirement(self):
        req = Requirement("this-package-does-not-exist")
        conflict = get_dependency_conflicts([req])
        self.assertTrue(conflict is not None)
        self.assertTrue(isinstance(conflict, DependencyConflict))
        self.assertEqual(
            str(conflict),
            'This instrumentation only instruments "this-package-does-not-exist", but no installed version was found, so nothing can be instrumented.',
        )

    def test_get_dependency_conflicts_not_installed(self):
        conflict = get_dependency_conflicts(["this-package-does-not-exist"])
        self.assertTrue(conflict is not None)
        self.assertTrue(isinstance(conflict, DependencyConflict))
        self.assertEqual(
            str(conflict),
            'This instrumentation only instruments "this-package-does-not-exist", but no installed version was found, so nothing can be instrumented.',
        )

    def test_get_dependency_conflicts_mismatched_version(self):
        conflict = get_dependency_conflicts(["pytest == 5000"])
        self.assertTrue(conflict is not None)
        self.assertTrue(isinstance(conflict, DependencyConflict))
        self.assertEqual(
            str(conflict),
            f'This instrumentation only instruments "pytest == 5000", but currently installed version ("pytest {pytest.__version__}") falls outside of that range, so nothing can be instrumented.',
        )

    def test_get_dist_dependency_conflicts(self):
        class MockDistribution(Distribution):
            def locate_file(self, path):
                pass

            def read_text(self, filename):
                pass

            @property
            def requires(self):
                return ['test-pkg ~= 1.0; extra == "instruments"']

        dist = MockDistribution()

        conflict = get_dist_dependency_conflicts(dist)
        self.assertTrue(conflict is not None)
        self.assertTrue(isinstance(conflict, DependencyConflict))
        self.assertEqual(
            str(conflict),
            'This instrumentation only instruments "test-pkg~=1.0; extra == "instruments"", but no installed version was found, so nothing can be instrumented.',
        )

    def test_get_dist_dependency_conflicts_requires_none(self):
        class MockDistribution(Distribution):
            def locate_file(self, path):
                pass

            def read_text(self, filename):
                pass

            @property
            def requires(self):
                # TODO: make another test for returning something with a blank list for both and and or
                return None

        dist = MockDistribution()
        conflict = get_dist_dependency_conflicts(dist)
        self.assertTrue(conflict is None)

    @patch("opentelemetry.instrumentation.dependencies.version")
    def test_get_dist_dependency_conflicts_any(self, version_mock):
        class MockDistribution(Distribution):
            def locate_file(self, path):
                pass

            def read_text(self, filename):
                pass

            @property
            def requires(self):
                return [
                    'foo ~= 1.0; extra == "instruments-any"',
                    'bar ~= 1.0; extra == "instruments-any"',
                ]

        dist = MockDistribution()

        def version_side_effect(package_name):
            if package_name == "foo":
                raise PackageNotFoundError("foo not found")
            if package_name == "bar":
                return "1.0.0"
            raise PackageNotFoundError(f"{package_name} not found")

        version_mock.side_effect = version_side_effect
        conflict = get_dist_dependency_conflicts(dist)
        self.assertIsNone(conflict)

    @patch("opentelemetry.instrumentation.dependencies.version")
    def test_get_dist_dependency_conflicts_neither(self, version_mock):
        class MockDistribution(Distribution):
            def locate_file(self, path):
                pass

            def read_text(self, filename):
                pass

            @property
            def requires(self):
                return [
                    'foo ~= 1.0; extra == "instruments-any"',
                    'bar ~= 1.0; extra == "instruments-any"',
                ]

        dist = MockDistribution()
        # version_mock.side_effect = lambda x: "1.0.0" if x == "foo" else "2.0.0"
        # version_mock("foo").return_value = "2.0.0"
        version_mock.side_effect = PackageNotFoundError("not found")
        conflict = get_dist_dependency_conflicts(dist)
        self.assertTrue(conflict is not None)
        self.assertTrue(isinstance(conflict, DependencyConflict))
        self.assertEqual(
            str(conflict),
            """This instrumentation requires any of "foo~=1.0; extra == "instruments-any", bar~=1.0; extra == "instruments-any"", but none are installed, so nothing can be instrumented.""",
        )

    # Tests when both "and" and "either" dependencies are specified and both pass.
    @patch("opentelemetry.instrumentation.dependencies.version")
    def test_get_dist_dependency_conflicts_any_and(self, version_mock):
        class MockDistribution(Distribution):
            def locate_file(self, path):
                pass

            def read_text(self, filename):
                pass

            @property
            def requires(self):
                # This indicates the instrumentation requires (foo and (bar or baz)))
                return [
                    'foo ~= 1.0; extra == "instruments"',
                    'bar ~= 2.0; extra == "instruments-any"',
                    'baz ~= 3.0; extra == "instruments-any"',
                ]

        dist = MockDistribution()

        def version_side_effect(package_name):
            if package_name == "foo":
                return "1.2.0"
            if package_name == "bar":
                raise PackageNotFoundError("bar not found")
            if package_name == "baz":
                return "3.7.0"
            raise PackageNotFoundError(f"{package_name} not found")

        version_mock.side_effect = version_side_effect
        conflict = get_dist_dependency_conflicts(dist)
        self.assertIsNone(conflict)

    # Tests when both "and" and "either" dependencies are specified but the "and" dependencies fail to resolve.
    @patch("opentelemetry.instrumentation.dependencies.version")
    def test_get_dist_dependency_conflicts_any_and_failed(self, version_mock):
        class MockDistribution(Distribution):
            def locate_file(self, path):
                pass

            def read_text(self, filename):
                pass

            @property
            def requires(self):
                # This indicates the instrumentation requires (foo and (bar or baz)))
                return [
                    'foo ~= 1.0; extra == "instruments"',
                    'bar ~= 2.0; extra == "instruments-any"',
                    'baz ~= 3.0; extra == "instruments-any"',
                ]

        dist = MockDistribution()

        def version_side_effect(package_name):
            if package_name == "foo":
                raise PackageNotFoundError("foo not found")
            if package_name == "bar":
                raise PackageNotFoundError("bar not found")
            if package_name == "baz":
                return "3.7.0"
            raise PackageNotFoundError(f"{package_name} not found")

        version_mock.side_effect = version_side_effect
        conflict = get_dist_dependency_conflicts(dist)
        self.assertTrue(conflict is not None)
        self.assertTrue(isinstance(conflict, DependencyConflict))
        self.assertEqual(
            str(conflict),
            'This instrumentation only instruments "foo~=1.0; extra == "instruments"", but no installed version was found, so nothing can be instrumented.',
        )

    # Tests when both "and" and "either" dependencies are specified but the "either" dependencies fail to resolve.
    @patch("opentelemetry.instrumentation.dependencies.version")
    def test_get_dist_dependency_conflicts_and_any_failed(self, version_mock):
        class MockDistribution(Distribution):
            def locate_file(self, path):
                pass

            def read_text(self, filename):
                pass

            @property
            def requires(self):
                # This indicates the instrumentation requires (foo and (bar or baz)))
                return [
                    'foo ~= 1.0; extra == "instruments"',
                    'bar ~= 2.0; extra == "instruments-any"',
                    'baz ~= 3.0; extra == "instruments-any"',
                ]

        dist = MockDistribution()

        def version_side_effect(package_name):
            if package_name == "foo":
                return "1.7.0"
            if package_name == "bar":
                raise PackageNotFoundError("bar not found")
            if package_name == "baz":
                raise PackageNotFoundError("baz not found")
            raise PackageNotFoundError(f"{package_name} not found")

        version_mock.side_effect = version_side_effect
        conflict = get_dist_dependency_conflicts(dist)
        self.assertTrue(conflict is not None)
        self.assertTrue(isinstance(conflict, DependencyConflict))
        self.assertEqual(
            str(conflict),
            """This instrumentation requires any of "bar~=2.0; extra == "instruments-any", baz~=3.0; extra == "instruments-any"", but none are installed, so nothing can be instrumented.""",
        )

    def test_dependency_conflict_format_message(self):
        cases = [
            (
                "required_version_mismatch",
                DependencyConflict("google-genai>=1.32.0,<3", "google-genai 1.31.0"),
                "GoogleGenAIInstrumentor",
                True,
                'GoogleGenAIInstrumentor only instruments "google-genai>=1.32.0,<3", but currently installed version ("google-genai 1.31.0") falls outside of that range, so nothing can be instrumented.',
            ),
            (
                "required_not_installed",
                DependencyConflict("google-genai>=1.32.0,<3", None),
                "GoogleGenAIInstrumentor",
                False,
                'GoogleGenAIInstrumentor only instruments "google-genai>=1.32.0,<3", but no installed version was found, so nothing can be instrumented.',
            ),
            (
                "required_any_version_mismatch",
                DependencyConflict(
                    required_any=["psycopg2>=2.7.3.1", "psycopg2-binary>=2.7.3.1"],
                    found_any=["psycopg2 2.6.0"],
                ),
                "Psycopg2Instrumentor",
                True,
                'Psycopg2Instrumentor instruments any of "psycopg2>=2.7.3.1, psycopg2-binary>=2.7.3.1", but currently installed version(s) ("psycopg2 2.6.0") fall outside of that range, so nothing can be instrumented.',
            ),
            (
                "required_any_none_installed",
                DependencyConflict(
                    required_any=["kafka-python>=2.0,<3.0", "kafka-python-ng>=2.0,<3.0"],
                    found_any=[],
                ),
                "KafkaInstrumentor",
                False,
                'KafkaInstrumentor requires any of "kafka-python>=2.0,<3.0, kafka-python-ng>=2.0,<3.0", but none are installed, so nothing can be instrumented.',
            ),
            (
                "without_instrumentor_name",
                DependencyConflict("google-genai>=1.32.0,<3", "google-genai 1.31.0"),
                None,
                True,
                'This instrumentation only instruments "google-genai>=1.32.0,<3", but currently installed version ("google-genai 1.31.0") falls outside of that range, so nothing can be instrumented.',
            ),
        ]
        for name, conflict, instrumentor_name, is_version_conflict, expected_message in cases:
            with self.subTest(case=name):
                self.assertEqual(conflict._is_version_conflict, is_version_conflict)
                self.assertEqual(
                    conflict._format_message(instrumentor_name),
                    expected_message,
                )
                if instrumentor_name is None:
                    self.assertEqual(str(conflict), expected_message)

    def test_dependency_conflict_log(self):
        cases = [
            (
                "version_conflict",
                DependencyConflict("google-genai>=1.32.0,<3", "google-genai 1.31.0"),
                True,
                "error",
            ),
            (
                "not_installed",
                DependencyConflict("google-genai>=1.32.0,<3", None),
                False,
                "debug",
            ),
        ]
        for name, conflict, is_version_conflict, expected_level in cases:
            with self.subTest(case=name):
                self.assertEqual(conflict._is_version_conflict, is_version_conflict)
                mock_logger = Mock()
                conflict._log(mock_logger, "GoogleGenAIInstrumentor")
                expected_message = conflict._format_message("GoogleGenAIInstrumentor")
                if expected_level == "error":
                    mock_logger.error.assert_called_once_with(expected_message)
                    mock_logger.debug.assert_not_called()
                else:
                    mock_logger.debug.assert_called_once_with(expected_message)
                    mock_logger.error.assert_not_called()
