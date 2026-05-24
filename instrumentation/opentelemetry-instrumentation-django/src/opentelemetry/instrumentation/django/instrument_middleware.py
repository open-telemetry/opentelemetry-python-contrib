# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import inspect
from functools import wraps
from importlib import import_module
from inspect import iscoroutinefunction
from logging import getLogger
from typing import Any

from django.utils.deprecation import MiddlewareMixin
from django.utils.module_loading import import_string

from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.trace import SpanKind, Tracer

try:
    from wrapt import wrap_function_wrapper
except ImportError:
    pass

_logger = getLogger(__name__)

_wrapped_targets: list[tuple[Any, str]] = []


def instrument_middleware_classes(
    settings_middleware: list[str],
    tracer: Tracer,
) -> None:
    """Wrap all middleware in settings_middleware with span creation.

    Categorizes each middleware and applies the appropriate wrapping:
    - MiddlewareMixin subclasses: single class-level wrap on MiddlewareMixin.__call__/__acall__
    - Pure new-style classes: per-class wrap on __call__/__acall__
    - Function-based factories: wrap the factory to return a traced callable

    """
    has_mixin_subclass = False

    for mw_path in settings_middleware:
        try:
            cls_or_func = import_string(mw_path)
        except ImportError:
            _logger.debug(
                "Could not import middleware %s, skipping", mw_path
            )
            continue

        if not inspect.isclass(cls_or_func):
            _wrap_function_middleware(mw_path, tracer)
        elif issubclass(cls_or_func, MiddlewareMixin):
            has_mixin_subclass = True
        else:
            _wrap_newstyle_middleware(mw_path, cls_or_func, tracer)

    if has_mixin_subclass:
        _wrap_middleware_mixin(tracer)


def uninstrument_middleware_classes() -> None:
    """Remove all middleware span wrappers applied by instrument_middleware_classes."""
    for obj, attr in _wrapped_targets:
        unwrap(obj, attr)
    _wrapped_targets.clear()


# -- Category 1: MiddlewareMixin-based middleware --


def _wrap_middleware_mixin(tracer: Tracer) -> None:
    wrap_function_wrapper(
        "django.utils.deprecation",
        "MiddlewareMixin.__call__",
        _make_mixin_call_wrapper(tracer),
    )
    _wrapped_targets.append((MiddlewareMixin, "__call__"))

    if hasattr(MiddlewareMixin, "__acall__"):
        wrap_function_wrapper(
            "django.utils.deprecation",
            "MiddlewareMixin.__acall__",
            _make_mixin_acall_wrapper(tracer),
        )
        _wrapped_targets.append((MiddlewareMixin, "__acall__"))


def _make_mixin_call_wrapper(tracer: Tracer):
    def _traced_call(wrapped, instance, args, kwargs):
        if getattr(instance, "async_mode", False) or getattr(instance, "is_async", False):
            return wrapped(*args, **kwargs)
        middleware_name = type(instance).__qualname__
        with tracer.start_as_current_span(
            f"django.middleware {middleware_name}",
            kind=SpanKind.INTERNAL,
        ):
            return wrapped(*args, **kwargs)

    return _traced_call


def _make_mixin_acall_wrapper(tracer: Tracer):
    async def _traced_acall(wrapped, instance, args, kwargs):
        middleware_name = type(instance).__qualname__
        with tracer.start_as_current_span(
            f"django.middleware {middleware_name}",
            kind=SpanKind.INTERNAL,
        ):
            return await wrapped(*args, **kwargs)

    return _traced_acall


# -- Category 2: Pure new-style class middleware --


def _wrap_newstyle_middleware(
    mw_path: str, cls: type, tracer: Tracer
) -> None:
    module_path, class_name = mw_path.rsplit(".", 1)

    wrap_function_wrapper(
        module_path,
        f"{class_name}.__call__",
        _make_newstyle_call_wrapper(tracer),
    )
    _wrapped_targets.append((cls, "__call__"))

    if hasattr(cls, "__acall__") and "__acall__" in cls.__dict__:
        wrap_function_wrapper(
            module_path,
            f"{class_name}.__acall__",
            _make_newstyle_acall_wrapper(tracer),
        )
        _wrapped_targets.append((cls, "__acall__"))


def _make_newstyle_call_wrapper(tracer: Tracer):
    def _traced_call(wrapped, instance, args, kwargs):
        middleware_name = type(instance).__qualname__

        if iscoroutinefunction(wrapped):

            async def _traced():
                with tracer.start_as_current_span(
                    f"django.middleware {middleware_name}",
                    kind=SpanKind.INTERNAL,
                ):
                    return await wrapped(*args, **kwargs)

            return _traced()

        with tracer.start_as_current_span(
            f"django.middleware {middleware_name}",
            kind=SpanKind.INTERNAL,
        ):
            return wrapped(*args, **kwargs)

    return _traced_call


def _make_newstyle_acall_wrapper(tracer: Tracer):
    async def _traced_acall(wrapped, instance, args, kwargs):
        middleware_name = type(instance).__qualname__
        with tracer.start_as_current_span(
            f"django.middleware {middleware_name}",
            kind=SpanKind.INTERNAL,
        ):
            return await wrapped(*args, **kwargs)

    return _traced_acall


# -- Category 3: Function-based middleware factory --


def _wrap_function_middleware(mw_path: str, tracer: Tracer) -> None:
    module_path, func_name = mw_path.rsplit(".", 1)
    module = import_module(module_path)

    wrap_function_wrapper(
        module_path,
        func_name,
        _make_factory_wrapper(tracer),
    )
    _wrapped_targets.append((module, func_name))


def _make_factory_wrapper(tracer: Tracer):
    def _traced_factory(wrapped, instance, args, kwargs):
        inner_callable = wrapped(*args, **kwargs)
        middleware_name = wrapped.__qualname__

        if iscoroutinefunction(inner_callable):

            @wraps(inner_callable)
            async def traced_async(request):
                with tracer.start_as_current_span(
                    f"django.middleware {middleware_name}",
                    kind=SpanKind.INTERNAL,
                ):
                    return await inner_callable(request)

            return traced_async
        else:

            @wraps(inner_callable)
            def traced_sync(request):
                with tracer.start_as_current_span(
                    f"django.middleware {middleware_name}",
                    kind=SpanKind.INTERNAL,
                ):
                    return inner_callable(request)

            return traced_sync

    return _traced_factory
