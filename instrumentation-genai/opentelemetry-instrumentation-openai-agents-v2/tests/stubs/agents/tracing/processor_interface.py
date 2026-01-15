from __future__ import annotations


class TracingProcessor:
    def on_trace_start(self, trace):  # pragma: no cover - stub
        pass

    def on_trace_end(self, trace):  # pragma: no cover - stub
        pass

    def on_span_start(self, span):  # pragma: no cover - stub
        pass

    def on_span_end(self, span):  # pragma: no cover - stub
        pass

    def shutdown(self) -> None:  # pragma: no cover - stub
        pass

    def force_flush(self) -> None:  # pragma: no cover - stub
        pass
