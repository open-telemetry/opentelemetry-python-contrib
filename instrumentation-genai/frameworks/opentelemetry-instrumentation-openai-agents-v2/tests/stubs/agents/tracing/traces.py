from __future__ import annotations

from datetime import datetime


class Trace:
    def __init__(self, name: str, trace_id: str, processor) -> None:
        self.name = name
        self.trace_id = trace_id
        self._processor = processor
        self.started_at: str | None = None
        self.ended_at: str | None = None

    def start(self) -> None:
        if self.started_at is not None:
            return
        self.started_at = datetime.utcnow().isoformat() + "Z"
        self._processor.on_trace_start(self)

    def finish(self) -> None:
        if self.ended_at is not None:
            return
        self.ended_at = datetime.utcnow().isoformat() + "Z"
        self._processor.on_trace_end(self)

    def __enter__(self) -> "Trace":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.finish()
