# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations


class StreamBuffer:
    """Accumulates Cohere V2 chat streaming state across events."""

    def __init__(self) -> None:
        self.response_id: str | None = None
        self.finish_reason: str | None = None
        self.text_content: list[str] = []
        self.input_tokens: int | None = None
        self.output_tokens: int | None = None

    def append_text_content(self, content: str) -> None:
        self.text_content.append(content)
