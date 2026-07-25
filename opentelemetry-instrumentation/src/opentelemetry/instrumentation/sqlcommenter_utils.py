# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import itertools
import sys
from typing import TYPE_CHECKING, Any

from opentelemetry import context
from opentelemetry.instrumentation.utils import _url_quote

if sys.version_info >= (3, 14):
    from string.templatelib import Template as _Template
else:
    _Template = ()

if TYPE_CHECKING:
    if sys.version_info >= (3, 14):
        from string.templatelib import Template
    else:
        from typing import Never

        Template = Never
    from typing import overload

    @overload
    def _add_sql_comment(sql: str, **meta: Any) -> str: ...

    @overload
    def _add_sql_comment(sql: Template, **meta: Any) -> Template: ...


def _add_sql_comment(sql: str | Template, **meta: Any) -> str | Template:
    """
    Appends comments to the sql statement and returns it
    """
    meta.update(**_add_framework_tags())
    comment = _generate_sql_comment(**meta)

    if isinstance(sql, _Template):
        last = sql.strings[-1].rstrip()
        if last.endswith(";"):
            last = last[:-1] + comment + ";"
        else:
            last += comment
        args = [
            *itertools.chain.from_iterable(
                zip(sql.strings[:-1], sql.interpolations)
            ),
            last,
        ]
        return _Template(*args)

    sql = sql.rstrip()
    if sql.endswith(";"):
        sql = sql[:-1] + comment + ";"
    else:
        sql = sql + comment
    return sql


def _generate_sql_comment(**meta) -> str:
    """
    Return a SQL comment with comma delimited key=value pairs created from
    **meta kwargs.
    """
    key_value_delimiter = ","

    if not meta:  # No entries added.
        return ""

    # Sort the keywords to ensure that caching works and that testing is
    # deterministic. It eases visual inspection as well.
    return (
        " /*"
        + key_value_delimiter.join(
            f"{_url_quote(key)}={_url_quote(value)!r}"
            for key, value in sorted(meta.items())
            if value is not None
        )
        + "*/"
    )


def _add_framework_tags() -> dict:
    """
    Returns orm related tags if any set by the context
    """

    sqlcommenter_framework_values = (
        context.get_value("SQLCOMMENTER_ORM_TAGS_AND_VALUES")
        if context.get_value("SQLCOMMENTER_ORM_TAGS_AND_VALUES")
        else {}
    )
    return sqlcommenter_framework_values
