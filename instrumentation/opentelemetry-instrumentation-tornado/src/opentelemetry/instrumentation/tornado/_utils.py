# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import inspect
from typing import Any

from tornado import httputil
from tornado.routing import Router, Rule
from tornado.web import RequestHandler

# Distinguishes "keep scanning sibling rules" from "matched a branch we can't
# inspect further, so stop and report no reliable result".
_NOT_FOUND = object()


def find_matched_rule(handler: RequestHandler) -> Rule | None:
    result = _find_rule(
        handler.application.default_router,
        handler.request,
        handler.__class__,
    )
    return None if result is _NOT_FOUND else result


# pylint: disable=too-many-return-statements
def _find_rule(
    router: Any,
    request: httputil.HTTPServerRequest,
    handler_class: type[RequestHandler],
) -> Rule | _NOT_FOUND | None:
    rules = getattr(router, "rules", None)
    if rules is None:
        # Opaque custom router; cannot inspect reliably.
        return _NOT_FOUND

    for rule in rules:
        params = rule.matcher.match(request)
        if params is None:
            continue
        target = getattr(rule, "target", None)
        if _is_handler_target(target):
            if target is handler_class:
                return rule
            # A different handler matched first, so Tornado would stop here too.
            return _NOT_FOUND
        if hasattr(target, "rules"):
            nested = _find_rule(target, request, handler_class)
            if nested is None:
                # Nested router did not resolve anything; keep scanning siblings.
                continue
            return nested
        if isinstance(target, Router):
            # Custom nested router matched, but we cannot see inside it.
            return _NOT_FOUND
        # Callable / connection delegate / other terminal target.
        return _NOT_FOUND
    return None


def _is_handler_target(target: Any) -> bool:
    return isinstance(target, type) and issubclass(target, RequestHandler)


def route_from_rule(rule: Rule, handler: RequestHandler) -> str | None:
    """Return a path with the dynamic parts as named parameters to reduce cardinality"""
    route = None
    if not hasattr(rule.matcher, "_find_groups"):
        return None

    format_str, num_params = rule.matcher._find_groups()
    if num_params is None:
        return None

    if num_params == 0:
        # for regex routes without captured parameters, use the matcher format string
        # to preserve a low-cardinality route value
        return format_str

    method = getattr(handler, handler.request.method.lower())
    # wrap the parameters with curly brackets so we can distinguish them from the fixed path
    method_args = tuple(f"{{{param}}}" for param in inspect.signature(method).parameters.keys())
    if len(method_args) == num_params:
        route = format_str % method_args
    else:
        route = format_str
    return route
