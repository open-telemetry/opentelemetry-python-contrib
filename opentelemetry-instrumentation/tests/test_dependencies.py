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

# pylint: disable=protected-access

from unittest.mock import patch

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
            'DependencyConflict: requested: "this-package-does-not-exist" but found: "None"',
        )

    def test_get_dependency_conflicts_not_installed(self):
        conflict = get_dependency_conflicts(["this-package-does-not-exist"])
        self.assertTrue(conflict is not None)
        self.assertTrue(isinstance(conflict, DependencyConflict))
        self.assertEqual(
            str(conflict),
            'DependencyConflict: requested: "this-package-does-not-exist" but found: "None"',
        )

    def test_get_dependency_conflicts_mismatched_version(self):
        conflict = get_dependency_conflicts(["pytest == 5000"])
        self.assertTrue(conflict is not None)
        self.assertTrue(isinstance(conflict, DependencyConflict))
        self.assertEqual(
            str(conflict),
            f'DependencyConflict: requested: "pytest == 5000" but found: "pytest {pytest.__version__}"',
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
            'DependencyConflict: requested: "test-pkg~=1.0; extra == "instruments"" but found: "None"',
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
            '''DependencyConflict: requested any of the following: "['foo~=1.0; extra == "instruments-any"', 'bar~=1.0; extra == "instruments-any"']" but found: "[]"''',
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
            'DependencyConflict: requested: "foo~=1.0; extra == "instruments"" but found: "None"',
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
            '''DependencyConflict: requested any of the following: "['bar~=2.0; extra == "instruments-any"', 'baz~=3.0; extra == "instruments-any"']" but found: "[]"''',
        )
