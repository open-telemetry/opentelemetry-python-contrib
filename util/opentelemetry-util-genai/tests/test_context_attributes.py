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

from __future__ import annotations

from unittest import TestCase

from opentelemetry import context as otel_context
from opentelemetry.util.genai.context_attributes import (
    get_context_scoped_attributes,
    set_context_scoped_attributes,
)


class TestSetContextScopedAttributes(TestCase):
    def test_returns_new_context(self) -> None:
        original = otel_context.get_current()
        new_ctx = set_context_scoped_attributes({"key": "value"}, original)
        self.assertIsNot(new_ctx, original)

    def test_values_readable_from_new_context(self) -> None:
        ctx = set_context_scoped_attributes({"gen_ai.workflow.name": "wf1"})
        attrs = get_context_scoped_attributes(ctx)
        self.assertEqual(attrs["gen_ai.workflow.name"], "wf1")

    def test_multiple_attributes_stored(self) -> None:
        ctx = set_context_scoped_attributes({"a": "1", "b": "2"})
        attrs = get_context_scoped_attributes(ctx)
        self.assertEqual(attrs["a"], "1")
        self.assertEqual(attrs["b"], "2")

    def test_existing_key_not_overwritten(self) -> None:
        """Lower-priority semantics: a key already in context is not replaced."""
        ctx = set_context_scoped_attributes({"gen_ai.workflow.name": "original"})
        ctx2 = set_context_scoped_attributes(
            {"gen_ai.workflow.name": "new_value"}, ctx
        )
        attrs = get_context_scoped_attributes(ctx2)
        self.assertEqual(attrs["gen_ai.workflow.name"], "original")

    def test_new_key_added_alongside_existing(self) -> None:
        ctx = set_context_scoped_attributes({"first": "a"})
        ctx2 = set_context_scoped_attributes({"second": "b"}, ctx)
        attrs = get_context_scoped_attributes(ctx2)
        self.assertEqual(attrs["first"], "a")
        self.assertEqual(attrs["second"], "b")

    def test_defaults_to_current_context(self) -> None:
        """set_context_scoped_attributes without explicit context uses current."""
        ctx = set_context_scoped_attributes({"implicit": "yes"})
        token = otel_context.attach(ctx)
        try:
            attrs = get_context_scoped_attributes()
            self.assertEqual(attrs["implicit"], "yes")
        finally:
            otel_context.detach(token)


class TestGetContextScopedAttributes(TestCase):
    def test_empty_context_returns_empty_dict(self) -> None:
        fresh_ctx = otel_context.get_current()
        attrs = get_context_scoped_attributes(fresh_ctx)
        self.assertEqual(attrs, {})

    def test_no_argument_uses_current_context(self) -> None:
        """get_context_scoped_attributes() with no arg reads current context."""
        ctx = set_context_scoped_attributes({"k": "v"})
        token = otel_context.attach(ctx)
        try:
            attrs = get_context_scoped_attributes()
            self.assertEqual(attrs["k"], "v")
        finally:
            otel_context.detach(token)

    def test_returns_same_dict_instance(self) -> None:
        """get_context_scoped_attributes returns the stored dict (same reference)."""
        ctx = set_context_scoped_attributes({"x": "1"})
        attrs1 = get_context_scoped_attributes(ctx)
        attrs2 = get_context_scoped_attributes(ctx)
        self.assertIs(attrs1, attrs2)
