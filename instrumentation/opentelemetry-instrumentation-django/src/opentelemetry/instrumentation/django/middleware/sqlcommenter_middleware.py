#!/usr/bin/python
#
# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import absolute_import

import logging
import sys

if sys.version_info.major <= 2:
    import urllib

    url_quote_fn = urllib.quote
else:
    import urllib.parse

    url_quote_fn = urllib.parse.quote

import django
from django.db import connection
from django.db.backends.utils import CursorDebugWrapper

try:
    from opentelemetry.trace.propagation.tracecontext import (
        TraceContextTextMapPropagator,
    )

    propagator = TraceContextTextMapPropagator()
except ImportError:
    propagator = None

django_version = django.get_version()
logger = logging.getLogger(__name__)

KEY_VALUE_DELIMITER = ","


class SqlCommenter:
    """
    Middleware to append a comment to each database query with details about
    the framework and the execution context.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        with connection.execute_wrapper(QueryWrapper(request)):
            return self.get_response(request)


class QueryWrapper:
    def __init__(self, request):
        self.request = request

    def __call__(self, execute, sql, params, many, context):
        _with_framework = getattr(
            django.conf.settings, "SQLCOMMENTER_WITH_FRAMEWORK", True
        )
        _with_controller = getattr(
            django.conf.settings, "SQLCOMMENTER_WITH_CONTROLLER", True
        )
        _with_route = getattr(
            django.conf.settings, "SQLCOMMENTER_WITH_ROUTE", True
        )
        _with_app_name = getattr(
            django.conf.settings, "SQLCOMMENTER_WITH_APP_NAME", False
        )
        _with_opencensus = getattr(
            django.conf.settings, "SQLCOMMENTER_WITH_OPENCENSUS", False
        )
        _with_opentelemetry = getattr(
            django.conf.settings, "SQLCOMMENTER_WITH_OPENTELEMETRY", False
        )
        _with_db_driver = getattr(
            django.conf.settings, "SQLCOMMENTER_WITH_DB_DRIVER", False
        )

        if _with_opencensus and _with_opentelemetry:
            logger.warning(
                "SQLCOMMENTER_WITH_OPENCENSUS and SQLCOMMENTER_WITH_OPENTELEMETRY were enabled. "
                "Only use one to avoid unexpected behavior"
            )

        _db_driver = context["connection"].settings_dict.get("ENGINE", "")
        _resolver_match = self.request.resolver_match

        _sql_comment = _generate_sql_comment(
            # Information about the controller.
            controller=_resolver_match.view_name
            if _resolver_match and _with_controller
            else None,
            # route is the pattern that matched a request with a controller i.e. the regex
            # See https://docs.djangoproject.com/en/stable/ref/urlresolvers/#django.urls.ResolverMatch.route
            # getattr() because the attribute doesn't exist in Django < 2.2.
            route=getattr(_resolver_match, "route", None)
            if _resolver_match and _with_route
            else None,
            # app_name is the application namespace for the URL pattern that matches the URL.
            # See https://docs.djangoproject.com/en/stable/ref/urlresolvers/#django.urls.ResolverMatch.app_name
            app_name=(_resolver_match.app_name or None)
            if _resolver_match and _with_app_name
            else None,
            # Framework centric information.
            framework=("django:%s" % django_version)
            if _with_framework
            else None,
            # Information about the database and driver.
            db_driver=_db_driver if _with_db_driver else None,
            **_get_opentelemetry_values() if _with_opentelemetry else {}
        )

        # TODO: MySQL truncates logs > 1024B so prepend comments
        # instead of statements, if the engine is MySQL.
        # See:
        #  * https://github.com/basecamp/marginalia/issues/61
        #  * https://github.com/basecamp/marginalia/pull/80
        sql += _sql_comment

        # Add the query to the query log if debugging.
        if context["cursor"].__class__ is CursorDebugWrapper:
            context["connection"].queries_log.append(sql)

        return execute(sql, params, many, context)


def _generate_sql_comment(**meta):
    """
    Return a SQL comment with comma delimited key=value pairs created from
    **meta kwargs.
    """
    if not meta:  # No entries added.
        return ""

    # Sort the keywords to ensure that caching works and that testing is
    # deterministic. It eases visual inspection as well.
    return (
        " /*"
        + KEY_VALUE_DELIMITER.join(
            "{}={!r}".format(_url_quote(key), _url_quote(value))
            for key, value in sorted(meta.items())
            if value is not None
        )
        + "*/"
    )


def _url_quote(s):
    if not isinstance(s, (str, bytes)):
        return s
    _quoted = url_quote_fn(s)
    # Since SQL uses '%' as a keyword, '%' is a by-product of url quoting
    # e.g. foo,bar --> foo%2Cbar
    # thus in our quoting, we need to escape it too to finally give
    #      foo,bar --> foo%%2Cbar
    return _quoted.replace("%", "%%")


def _get_opentelemetry_values():
    """
    Return the OpenTelemetry Trace and Span IDs if Span ID is set in the
    OpenTelemetry execution context.
    """
    if propagator:
        # Insert the W3C TraceContext generated
        _headers = {}
        propagator.inject(_headers)
        return _headers
    else:
        raise ImportError("OpenTelemetry is not installed.")
