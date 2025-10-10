from __future__ import annotations

from datetime import datetime
from typing import Any


class Span:
    def __init__(
        self,
        trace_id: str,
        span_id: str,
        span_data: Any,
        parent_id: str | None,
        processor,
    ) -> None:
        self.trace_id = trace_id
        self.span_id = span_id
        self.span_data = span_data
        self.parent_id = parent_id
        self.started_at: str | None = None
        self.ended_at: str | None = None
        self.error = None
        self._processor = processor

    def start(self) -> None:
        if self.started_at is not None:
            return
        self.started_at = datetime.utcnow().isoformat() + "Z"
        self._processor.on_span_start(self)

    def finish(self) -> None:
        if self.ended_at is not None:
            return
        self.ended_at = datetime.utcnow().isoformat() + "Z"
        self._processor.on_span_end(self)

    def __enter__(self) -> "Span":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.finish()
