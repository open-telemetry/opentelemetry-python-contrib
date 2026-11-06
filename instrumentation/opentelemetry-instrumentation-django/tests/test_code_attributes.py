# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from functools import partial
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from opentelemetry.instrumentation.django.middleware.otel_middleware import (
    _collect_code_attributes,
)
from opentelemetry.semconv.attributes.code_attributes import (
    CODE_FILE_PATH,
    CODE_FUNCTION_NAME,
    CODE_LINE_NUMBER,
)

from .views import TracedClassView, _pass_through_decorator, traced


class TestCollectCodeAttributes(TestCase):
    def test_mixed_class_view_wrappers(self) -> None:
        dispatch = TracedClassView.dispatch
        with patch.object(
            TracedClassView,
            "dispatch",
            _pass_through_decorator(partial(dispatch)),
        ):
            view = TracedClassView.as_view()
            for target in (
                view,
                _pass_through_decorator(view),
                _pass_through_decorator(partial(_pass_through_decorator(partial(view)))),
            ):
                with self.subTest(target=target):
                    attributes = _collect_code_attributes(target)
                    self.assertEqual(
                        attributes,
                        {
                            CODE_FUNCTION_NAME: f"{dispatch.__module__}.{dispatch.__qualname__}",
                            CODE_FILE_PATH: dispatch.__code__.co_filename,
                            CODE_LINE_NUMBER: dispatch.__code__.co_firstlineno,
                        },
                    )
                    self.assertIs(type(attributes[CODE_FUNCTION_NAME]), str)
                    self.assertIs(type(attributes[CODE_FILE_PATH]), str)
                    self.assertIs(type(attributes[CODE_LINE_NUMBER]), int)

    def test_wrapper_cycles(self) -> None:
        for attribute, target in (
            ("__wrapped__", traced),
            ("__wrapped__", _pass_through_decorator(traced)),
            ("__wrapped__", partial(traced)),
            ("view_class", SimpleNamespace(dispatch=traced)),
        ):
            with (
                self.subTest(attribute=attribute, target=target),
                patch.object(traced, attribute, target, create=True),
            ):
                self.assertEqual(_collect_code_attributes(traced), {})

    def test_invalid_view_class(self) -> None:
        with patch.object(traced, "view_class", object(), create=True):
            self.assertEqual(_collect_code_attributes(traced), {})

    def test_callable_view(self) -> None:
        class CallableView:
            def __call__(self) -> None:
                return None

        call = CallableView.__call__
        attributes = _collect_code_attributes(CallableView())
        self.assertEqual(
            attributes,
            {
                CODE_FUNCTION_NAME: f"{call.__module__}.{call.__qualname__}",
                CODE_FILE_PATH: call.__code__.co_filename,
                CODE_LINE_NUMBER: call.__code__.co_firstlineno,
            },
        )
        self.assertIs(type(attributes[CODE_FUNCTION_NAME]), str)
        self.assertIs(type(attributes[CODE_FILE_PATH]), str)
        self.assertIs(type(attributes[CODE_LINE_NUMBER]), int)
