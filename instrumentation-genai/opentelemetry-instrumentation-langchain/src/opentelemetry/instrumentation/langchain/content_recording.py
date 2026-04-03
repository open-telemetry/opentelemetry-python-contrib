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

"""Thin integration layer over the shared genai content capture utilities.

Provides clear APIs for the LangChain callback handler to decide what
content should be recorded on spans and events.
"""

from typing import Optional

from opentelemetry.util.genai.types import ContentCapturingMode
from opentelemetry.util.genai.utils import (
    get_content_capturing_mode,
    is_experimental_mode,
    should_emit_event,
)


class ContentPolicy:
    """Determines what content should be recorded on spans and events.

    Wraps the shared genai utility functions to provide a clean API
    for the callback handler. All properties are evaluated lazily so
    that environment variable changes are picked up immediately.
    """

    @property
    def should_record_content_on_spans(self) -> bool:
        """Whether message/tool content should be recorded as span attributes."""
        return self.mode in (
            ContentCapturingMode.SPAN_ONLY,
            ContentCapturingMode.SPAN_AND_EVENT,
        )

    @property
    def should_emit_events(self) -> bool:
        """Whether content events should be emitted."""
        return should_emit_event()

    @property
    def record_content(self) -> bool:
        """Whether content should be recorded at all (spans or events)."""
        return self.should_record_content_on_spans or self.should_emit_events

    @property
    def mode(self) -> ContentCapturingMode:
        """The current content capturing mode.

        Returns ``NO_CONTENT`` when not running in experimental mode.
        """
        if not is_experimental_mode():
            return ContentCapturingMode.NO_CONTENT
        return get_content_capturing_mode()


# -- Helper functions for specific content types ------------------------------
# All opt-in content types follow the same underlying policy today.  Separate
# helpers are provided so call-sites read clearly and so that per-type
# overrides can be added later without changing every caller.


def should_record_messages(policy: ContentPolicy) -> bool:
    """Whether input/output messages should be recorded on spans."""
    return policy.should_record_content_on_spans


def should_record_tool_content(policy: ContentPolicy) -> bool:
    """Whether tool arguments and results should be recorded on spans."""
    return policy.should_record_content_on_spans


def should_record_retriever_content(policy: ContentPolicy) -> bool:
    """Whether retriever queries and document content should be recorded."""
    return policy.should_record_content_on_spans


def should_record_system_instructions(policy: ContentPolicy) -> bool:
    """Whether system instructions should be recorded on spans."""
    return policy.should_record_content_on_spans


# -- Default singleton --------------------------------------------------------

_default_policy: Optional[ContentPolicy] = None


def get_content_policy() -> ContentPolicy:
    """Get the content policy based on current environment configuration.

    Returns a module-level singleton.  Because the policy reads
    environment variables lazily on every property access, a single
    instance is sufficient.
    """
    global _default_policy  # noqa: PLW0603
    if _default_policy is None:
        _default_policy = ContentPolicy()
    return _default_policy
