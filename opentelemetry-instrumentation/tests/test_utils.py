# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import sys
import unittest
from http import HTTPStatus
from unittest import mock

import pytest
from wrapt import wrap_function_wrapper

try:
    # wrapt 2.0.0+
    from wrapt import BaseObjectProxy  # pylint: disable=no-name-in-module
except ImportError:
    from wrapt import ObjectProxy as BaseObjectProxy

from opentelemetry.context import (
    _SUPPRESS_HTTP_INSTRUMENTATION_KEY,
    _SUPPRESS_INSTRUMENTATION_KEY,
    get_current,
    get_value,
)
from opentelemetry.instrumentation.sqlcommenter_utils import _add_sql_comment
from opentelemetry.instrumentation.utils import (
    _python_path_without_directory,
    http_status_to_status_code,
    is_http_instrumentation_enabled,
    is_instrumentation_enabled,
    suppress_http_instrumentation,
    suppress_instrumentation,
    unwrap,
)
from opentelemetry.trace import StatusCode


class _MockInterpolation:
    def __init__(self, expression: str) -> None:
        self.expression = expression


class _MockTemplate:
    """Mock for string.templatelib.Template"""

    def __init__(self, *args) -> None:
        strings: list[str] = []
        interpolations: list[_MockInterpolation] = []
        for arg in args:
            if isinstance(arg, str):
                strings.append(arg)
            else:
                interpolations.append(arg)
        self.strings = tuple(strings)
        self.interpolations = interpolations


class WrappedClass:
    def method(self):
        pass

    def wrapper_method(self):
        pass


# pylint: disable=too-many-public-methods
class TestUtils(unittest.TestCase):
    # See https://github.com/open-telemetry/opentelemetry-specification/blob/main/specification/trace
    # /semantic_conventions/http.md#status
    def test_http_status_to_status_code(self):
        for status_code, expected in (
            (HTTPStatus.OK, StatusCode.UNSET),
            (HTTPStatus.ACCEPTED, StatusCode.UNSET),
            (HTTPStatus.IM_USED, StatusCode.UNSET),
            (HTTPStatus.MULTIPLE_CHOICES, StatusCode.UNSET),
            (HTTPStatus.BAD_REQUEST, StatusCode.ERROR),
            (HTTPStatus.UNAUTHORIZED, StatusCode.ERROR),
            (HTTPStatus.FORBIDDEN, StatusCode.ERROR),
            (HTTPStatus.NOT_FOUND, StatusCode.ERROR),
            (
                HTTPStatus.UNPROCESSABLE_ENTITY,
                StatusCode.ERROR,
            ),
            (
                HTTPStatus.TOO_MANY_REQUESTS,
                StatusCode.ERROR,
            ),
            (HTTPStatus.NOT_IMPLEMENTED, StatusCode.ERROR),
            (HTTPStatus.SERVICE_UNAVAILABLE, StatusCode.ERROR),
            (
                HTTPStatus.GATEWAY_TIMEOUT,
                StatusCode.ERROR,
            ),
            (
                HTTPStatus.HTTP_VERSION_NOT_SUPPORTED,
                StatusCode.ERROR,
            ),
            (600, StatusCode.ERROR),
            (99, StatusCode.ERROR),
        ):
            with self.subTest(status_code=status_code):
                actual = http_status_to_status_code(int(status_code))
                self.assertEqual(actual, expected, status_code)

    def test_http_status_to_status_code_none(self):
        for status_code, expected in ((None, StatusCode.UNSET),):
            with self.subTest(status_code=status_code):
                actual = http_status_to_status_code(status_code)
                self.assertEqual(actual, expected, status_code)

    def test_http_status_to_status_code_redirect(self):
        for status_code, expected in (
            (HTTPStatus.MULTIPLE_CHOICES, StatusCode.ERROR),
            (HTTPStatus.MOVED_PERMANENTLY, StatusCode.ERROR),
            (HTTPStatus.TEMPORARY_REDIRECT, StatusCode.ERROR),
            (HTTPStatus.PERMANENT_REDIRECT, StatusCode.ERROR),
        ):
            with self.subTest(status_code=status_code):
                actual = http_status_to_status_code(int(status_code), allow_redirect=False)
                self.assertEqual(actual, expected, status_code)

    def test_http_status_to_status_code_server(self):
        for status_code, expected in (
            (HTTPStatus.OK, StatusCode.UNSET),
            (HTTPStatus.ACCEPTED, StatusCode.UNSET),
            (HTTPStatus.IM_USED, StatusCode.UNSET),
            (HTTPStatus.MULTIPLE_CHOICES, StatusCode.UNSET),
            (HTTPStatus.BAD_REQUEST, StatusCode.UNSET),
            (HTTPStatus.UNAUTHORIZED, StatusCode.UNSET),
            (HTTPStatus.FORBIDDEN, StatusCode.UNSET),
            (HTTPStatus.NOT_FOUND, StatusCode.UNSET),
            (
                HTTPStatus.UNPROCESSABLE_ENTITY,
                StatusCode.UNSET,
            ),
            (
                HTTPStatus.TOO_MANY_REQUESTS,
                StatusCode.UNSET,
            ),
            (HTTPStatus.NOT_IMPLEMENTED, StatusCode.ERROR),
            (HTTPStatus.SERVICE_UNAVAILABLE, StatusCode.ERROR),
            (
                HTTPStatus.GATEWAY_TIMEOUT,
                StatusCode.ERROR,
            ),
            (
                HTTPStatus.HTTP_VERSION_NOT_SUPPORTED,
                StatusCode.ERROR,
            ),
            (600, StatusCode.ERROR),
            (99, StatusCode.ERROR),
        ):
            with self.subTest(status_code=status_code):
                actual = http_status_to_status_code(int(status_code), server_span=True)
                self.assertEqual(actual, expected, status_code)

    def test_remove_current_directory_from_python_path_windows(self):
        directory = (
            r"c:\users\Trayvon Martin\workplace\opentelemetry-python-contrib"
            r"\opentelemetry-instrumentation\src\opentelemetry\instrumentation\auto_instrumentation"
        )
        path_separator = r";"
        python_path = (
            r"c:\users\Trayvon Martin\workplace\opentelemetry-python-contrib"
            r"\opentelemetry-instrumentation\src\opentelemetry\instrumentation\auto_instrumentation"
            r";C:\Users\trayvonmartin\workplace"
        )
        actual_python_path = _python_path_without_directory(python_path, directory, path_separator)
        expected_python_path = r"C:\Users\trayvonmartin\workplace"
        self.assertEqual(actual_python_path, expected_python_path)

    def test_remove_current_directory_from_python_path_linux(self):
        directory = (
            r"/home/georgefloyd/workplace/opentelemetry-python-contrib"
            r"/opentelemetry-instrumentation/src/opentelemetry/instrumentation/auto_instrumentation"
        )
        path_separator = r":"
        python_path = (
            r"/home/georgefloyd/workplace/opentelemetry-python-contrib"
            r"/opentelemetry-instrumentation/src/opentelemetry/instrumentation/auto_instrumentation"
            r":/home/georgefloyd/workplace"
        )
        actual_python_path = _python_path_without_directory(python_path, directory, path_separator)
        expected_python_path = r"/home/georgefloyd/workplace"
        self.assertEqual(actual_python_path, expected_python_path)

    def test_remove_current_directory_from_python_path_windows_only_path(self):
        directory = (
            r"c:\users\Charleena Lyles\workplace\opentelemetry-python-contrib"
            r"\opentelemetry-instrumentation\src\opentelemetry\instrumentation\auto_instrumentation"
        )
        path_separator = r";"
        python_path = (
            r"c:\users\Charleena Lyles\workplace\opentelemetry-python-contrib"
            r"\opentelemetry-instrumentation\src\opentelemetry\instrumentation\auto_instrumentation"
        )
        actual_python_path = _python_path_without_directory(python_path, directory, path_separator)
        self.assertEqual(actual_python_path, python_path)

    def test_remove_current_directory_from_python_path_linux_only_path(self):
        directory = (
            r"/home/SandraBland/workplace/opentelemetry-python-contrib"
            r"/opentelemetry-instrumentation/src/opentelemetry/instrumentation/auto_instrumentation"
        )
        path_separator = r":"
        python_path = (
            r"/home/SandraBland/workplace/opentelemetry-python-contrib"
            r"/opentelemetry-instrumentation/src/opentelemetry/instrumentation/auto_instrumentation"
        )
        actual_python_path = _python_path_without_directory(python_path, directory, path_separator)
        self.assertEqual(actual_python_path, python_path)

    def test_add_sql_comments_with_semicolon(self):
        sql_query_without_semicolon = "Select 1;"
        comments = {"comment_1": "value 1", "comment 2": "value 3"}
        commented_sql_without_semicolon = _add_sql_comment(sql_query_without_semicolon, **comments)

        self.assertEqual(
            commented_sql_without_semicolon,
            "Select 1 /*comment%%202='value%%203',comment_1='value%%201'*/;",
        )

    def test_add_sql_comments_without_semicolon(self):
        sql_query_without_semicolon = "Select 1"
        comments = {"comment_1": "value 1", "comment 2": "value 3"}
        commented_sql_without_semicolon = _add_sql_comment(sql_query_without_semicolon, **comments)

        self.assertEqual(
            commented_sql_without_semicolon,
            "Select 1 /*comment%%202='value%%203',comment_1='value%%201'*/",
        )

    def test_add_sql_comments_without_comments(self):
        sql_query_without_semicolon = "Select 1"
        comments = {}
        commented_sql_without_semicolon = _add_sql_comment(sql_query_without_semicolon, **comments)

        self.assertEqual(commented_sql_without_semicolon, "Select 1")

    @mock.patch(
        "opentelemetry.instrumentation.sqlcommenter_utils._Template",
        _MockTemplate,
    )
    def test_add_sql_comment_t_string_without_semicolon(self):
        template = _MockTemplate("SELECT ", _MockInterpolation("val"), " FROM foo")
        result = _add_sql_comment(template, k="v")
        self.assertIsInstance(result, _MockTemplate)
        self.assertEqual(result.strings, ("SELECT ", " FROM foo /*k='v'*/"))
        self.assertEqual(result.interpolations[0].expression, "val")

    @mock.patch(
        "opentelemetry.instrumentation.sqlcommenter_utils._Template",
        _MockTemplate,
    )
    def test_add_sql_comment_t_string_with_semicolon(self):
        template = _MockTemplate("SELECT ", _MockInterpolation("val"), " FROM foo;")
        result = _add_sql_comment(template, k="v")
        self.assertIsInstance(result, _MockTemplate)
        self.assertEqual(result.strings, ("SELECT ", " FROM foo /*k='v'*/;"))
        self.assertEqual(result.interpolations[0].expression, "val")

    @mock.patch(
        "opentelemetry.instrumentation.sqlcommenter_utils._Template",
        _MockTemplate,
    )
    def test_add_sql_comment_t_string_no_meta(self):
        template = _MockTemplate("SELECT ", _MockInterpolation("val"), " FROM foo")
        result = _add_sql_comment(template)
        self.assertIsInstance(result, _MockTemplate)
        self.assertEqual(result.strings, ("SELECT ", " FROM foo"))
        self.assertEqual(result.interpolations[0].expression, "val")

    @mock.patch(
        "opentelemetry.instrumentation.sqlcommenter_utils._Template",
        _MockTemplate,
    )
    def test_add_sql_comment_t_string_multiple_interpolations(self):
        template = _MockTemplate(
            "INSERT INTO t (a, b) VALUES (",
            _MockInterpolation("a"),
            ", ",
            _MockInterpolation("b"),
            ")",
        )
        result = _add_sql_comment(template, k="v")
        self.assertIsInstance(result, _MockTemplate)
        self.assertEqual(
            result.strings,
            ("INSERT INTO t (a, b) VALUES (", ", ", ") /*k='v'*/"),
        )
        self.assertEqual(result.interpolations[0].expression, "a")
        self.assertEqual(result.interpolations[1].expression, "b")

    @pytest.mark.skipif(
        sys.version_info < (3, 14),
        reason="requires Python 3.14+ for t-strings",
    )
    def test_add_sql_comment_real_t_string_without_semicolon(self):
        # pylint: disable-next=import-outside-toplevel
        from string.templatelib import Interpolation, Template  # noqa: PLC0415

        val = 42
        template = Template("SELECT ", Interpolation(val, "val"), " FROM foo")
        result = _add_sql_comment(template, k="v")
        self.assertIsInstance(result, Template)
        self.assertEqual(result.strings, ("SELECT ", " FROM foo /*k='v'*/"))
        self.assertEqual(result.interpolations[0].expression, "val")

    @pytest.mark.skipif(
        sys.version_info < (3, 14),
        reason="requires Python 3.14+ for t-strings",
    )
    def test_add_sql_comment_real_t_string_with_semicolon(self):
        # pylint: disable-next=import-outside-toplevel
        from string.templatelib import Interpolation, Template  # noqa: PLC0415

        val = 42
        template = Template("SELECT ", Interpolation(val, "val"), " FROM foo;")
        result = _add_sql_comment(template, k="v")
        self.assertIsInstance(result, Template)
        self.assertEqual(result.strings, ("SELECT ", " FROM foo /*k='v'*/;"))
        self.assertEqual(result.interpolations[0].expression, "val")

    def test_is_instrumentation_enabled_by_default(self):
        self.assertTrue(is_instrumentation_enabled())
        self.assertTrue(is_http_instrumentation_enabled())

    def test_suppress_instrumentation(self):
        with suppress_instrumentation():
            self.assertFalse(is_instrumentation_enabled())
            self.assertFalse(is_http_instrumentation_enabled())

        self.assertTrue(is_instrumentation_enabled())
        self.assertTrue(is_http_instrumentation_enabled())

    def test_suppress_http_instrumentation(self):
        with suppress_http_instrumentation():
            self.assertFalse(is_http_instrumentation_enabled())
            self.assertTrue(is_instrumentation_enabled())

        self.assertTrue(is_instrumentation_enabled())
        self.assertTrue(is_http_instrumentation_enabled())

    def test_suppress_instrumentation_key(self):
        self.assertIsNone(get_value(_SUPPRESS_INSTRUMENTATION_KEY))
        self.assertIsNone(get_value("suppress_instrumentation"))

        with suppress_instrumentation():
            ctx = get_current()
            self.assertIn(_SUPPRESS_INSTRUMENTATION_KEY, ctx)
            self.assertIn("suppress_instrumentation", ctx)
            self.assertTrue(get_value(_SUPPRESS_INSTRUMENTATION_KEY))
            self.assertTrue(get_value("suppress_instrumentation"))

        self.assertIsNone(get_value(_SUPPRESS_INSTRUMENTATION_KEY))
        self.assertIsNone(get_value("suppress_instrumentation"))

    def test_suppress_http_instrumentation_key(self):
        self.assertIsNone(get_value(_SUPPRESS_HTTP_INSTRUMENTATION_KEY))

        with suppress_http_instrumentation():
            ctx = get_current()
            self.assertIn(_SUPPRESS_HTTP_INSTRUMENTATION_KEY, ctx)
            self.assertTrue(get_value(_SUPPRESS_HTTP_INSTRUMENTATION_KEY))

        self.assertIsNone(get_value(_SUPPRESS_HTTP_INSTRUMENTATION_KEY))


class UnwrapTestCase(unittest.TestCase):
    @staticmethod
    def _wrap_method():
        return wrap_function_wrapper(WrappedClass, "method", WrappedClass.wrapper_method)

    def test_can_unwrap_object_attribute(self):
        self._wrap_method()
        instance = WrappedClass()
        self.assertTrue(isinstance(instance.method, BaseObjectProxy))

        unwrap(WrappedClass, "method")
        self.assertFalse(isinstance(instance.method, BaseObjectProxy))

    def test_can_unwrap_object_attribute_as_string(self):
        self._wrap_method()
        instance = WrappedClass()
        self.assertTrue(isinstance(instance.method, BaseObjectProxy))

        unwrap("tests.test_utils.WrappedClass", "method")
        self.assertFalse(isinstance(instance.method, BaseObjectProxy))

    def test_raises_import_error_if_path_not_well_formed(self):
        self._wrap_method()
        instance = WrappedClass()
        self.assertTrue(isinstance(instance.method, BaseObjectProxy))

        with self.assertRaisesRegex(ImportError, "Cannot parse '' as dotted import path"):
            unwrap("", "method")

        unwrap(WrappedClass, "method")
        self.assertFalse(isinstance(instance.method, BaseObjectProxy))

    def test_noop_if_module_not_imported(self):
        # A module that exists but hasn't been imported, treated
        # as no-op.
        self.assertNotIn("email.generator", sys.modules)
        unwrap("email.generator.BytesGenerator", "flatten")
        self.assertNotIn("email.generator", sys.modules)

    def test_noop_if_cannot_find_module(self):
        self._wrap_method()
        instance = WrappedClass()
        self.assertTrue(isinstance(instance.method, BaseObjectProxy))

        # Treated same as an existing module that hasn't been imported,
        # as a no-op.
        unwrap("does.not.exist.WrappedClass", "method")

        unwrap(WrappedClass, "method")
        self.assertFalse(isinstance(instance.method, BaseObjectProxy))

    def test_raises_import_error_if_cannot_find_object(self):
        self._wrap_method()
        instance = WrappedClass()
        self.assertTrue(isinstance(instance.method, BaseObjectProxy))

        with self.assertRaisesRegex(ImportError, "Cannot import 'NotWrappedClass' from"):
            unwrap("tests.test_utils.NotWrappedClass", "method")

        unwrap(WrappedClass, "method")
        self.assertFalse(isinstance(instance.method, BaseObjectProxy))

    # pylint: disable=no-self-use
    def test_does_nothing_if_cannot_find_attribute(self):
        instance = WrappedClass()
        unwrap(instance, "method_not_found")

    def test_does_nothing_if_attribute_is_not_from_wrapt(self):
        instance = WrappedClass()
        self.assertFalse(isinstance(instance.method, BaseObjectProxy))
        unwrap(WrappedClass, "method")
        self.assertFalse(isinstance(instance.method, BaseObjectProxy))
