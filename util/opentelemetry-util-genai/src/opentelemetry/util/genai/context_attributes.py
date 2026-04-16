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

"""
Local Context-Scoped Attributes (CSA) layer for GenAI instrumentation.

This module provides a process-local alternative to W3C Baggage for propagating
instrumentation attributes (e.g. ``gen_ai.workflow.name``) to child spans within
the same process.  It follows the API shape proposed by OTel spec PR #4931 so
migration to the upstream CSA implementation will be straightforward.

Key properties:
- Attributes are stored under a private OTel context key — they are **never**
  serialised into W3C Baggage headers or any outbound propagation format.
- Lower-priority semantics: keys already present in the context are **not**
  overwritten when new attributes are merged in.
"""

from __future__ import annotations

from typing import Any

from opentelemetry import context as otel_context
from opentelemetry.context import Context

_GENAI_CONTEXT_ATTRS_KEY = otel_context.create_key(
    "opentelemetry.util.genai.context_scoped_attrs"
)


def set_context_scoped_attributes(
    attrs: dict[str, Any],
    context: Context | None = None,
) -> Context:
    """Return a new Context with *attrs* merged in (existing keys win).

    Args:
        attrs: Attributes to add to the context.  Keys that are already
            present in the context are **not** overwritten (lower-priority
            semantics matching the CSA spec).
        context: Base context to merge into.  Defaults to the current context.

    Returns:
        A new :class:`~opentelemetry.context.Context` containing the merged
        attributes.  The caller is responsible for attaching it if needed.
    """
    ctx = context if context is not None else otel_context.get_current()
    existing: dict[str, Any] = (
        otel_context.get_value(_GENAI_CONTEXT_ATTRS_KEY, context=ctx) or {}
    )
    # existing keys win — new attrs fill in gaps only
    merged = {**attrs, **existing}
    return otel_context.set_value(_GENAI_CONTEXT_ATTRS_KEY, merged, ctx)


def get_context_scoped_attributes(
    context: Context | None = None,
) -> dict[str, Any]:
    """Return context-scoped attributes from *context*, or an empty dict.

    Args:
        context: Context to read from.  Defaults to the current context.

    Returns:
        A dict of attributes previously set via
        :func:`set_context_scoped_attributes`, or ``{}`` if none are present.
    """
    ctx = context if context is not None else otel_context.get_current()
    return otel_context.get_value(_GENAI_CONTEXT_ATTRS_KEY, context=ctx) or {}
