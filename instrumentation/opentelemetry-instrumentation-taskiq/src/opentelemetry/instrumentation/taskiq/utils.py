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

import logging
from typing import TYPE_CHECKING, Optional, Tuple

from taskiq import TaskiqMessage

from opentelemetry.trace import Span

if TYPE_CHECKING:
    from contextlib import AbstractContextManager

logger = logging.getLogger(__name__)

# Taskiq Context key
CTX_KEY = "__otel_task_span"

# Taskiq Context attributes
TASKIQ_CONTEXT_ATTRIBUTES = [
    "_retries",
    "delay",
    "max_retries",
    "retry_on_error",
    "timeout",
    "X-Taskiq-requeue",
]


# pylint:disable=too-many-branches
def set_attributes_from_context(span, context):
    """Helper to extract meta values from a Taskiq Context"""
    if not span.is_recording():
        return

    for key in TASKIQ_CONTEXT_ATTRIBUTES:
        value = context.get(key)

        # Skip this key if it is not set
        if value is None:
            continue

        # Skip `retries` if it's value is `0`
        if key == "_retries":
            if value == "0":
                continue

        attribute_name = f"taskiq.{key}"

        span.set_attribute(attribute_name, value)


def attach_context(
    message: Optional[TaskiqMessage],
    span: Span,
    activation: AbstractContextManager[Span],
    token: Optional[object],
    is_publish: bool = False,
) -> None:
    """Helper to propagate a `Span`, `ContextManager` and context token
    for the given `Task` instance. This function uses a `dict` that stores
    the Span using the `(task_id, is_publish)` as a key. This is useful
    when information must be propagated from one Celery signal to another.

    We use (task_id, is_publish) for the key to ensure that publishing a
    task from within another task does not cause any conflicts.

    This mostly happens when either a task fails and a retry policy is in place,
    we end up trying to publish a task with the same id as the task currently running.
    """
    if message is None:
        return

    ctx_dict = getattr(message, CTX_KEY, None)

    if ctx_dict is None:
        ctx_dict = {}
        setattr(message, CTX_KEY, ctx_dict)

    ctx_dict[(message.task_id, is_publish)] = (span, activation, token)


def detach_context(message: TaskiqMessage, is_publish: bool = False) -> None:
    """Helper to remove  `Span`, `ContextManager` and context token in a
    Taskiq task when it's propagated.
    This function handles tasks where no values are attached to the `Task`.
    """
    span_dict = getattr(message, CTX_KEY, None)
    if span_dict is None:
        return

    # See note in `attach_context` for key info
    span_dict.pop((message.task_id, is_publish), None)


def retrieve_context(
    message: TaskiqMessage, is_publish: bool = False
) -> Optional[Tuple[Span, AbstractContextManager[Span], Optional[object]]]:
    """Helper to retrieve an active `Span`, `ContextManager` and context token
    stored in a `TaskiqMessage` instance
    """
    span_dict = getattr(message, CTX_KEY, None)
    if span_dict is None:
        return None

    # See note in `attach_context` for key info
    return span_dict.get((message.task_id, is_publish), None)
