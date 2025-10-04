from __future__ import annotations

from typing import Protocol

from .types import GenAI


class CompletionCallback(Protocol):
    """Protocol implemented by handlers interested in completion events."""

    def on_completion(self, invocation: GenAI) -> None:
        """Handle completion of a GenAI invocation."""


__all__ = ["CompletionCallback"]
