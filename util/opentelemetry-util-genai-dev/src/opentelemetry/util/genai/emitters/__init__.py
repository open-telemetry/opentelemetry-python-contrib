"""Emitter package consolidating all telemetry signal emitters.

Exports:
    SpanEmitter
    MetricsEmitter
    ContentEventsEmitter
    TraceloopCompatEmitter
    CompositeGenerator (composition orchestrator; legacy name retained)

NOTE: CompositeGenerator name retained for backward compatibility with
previous documentation. Future rename to CompositeEmitter may introduce
an alias first.
"""

from __future__ import annotations

from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)

from .composite import CompositeGenerator  # noqa: F401
from .content_events import ContentEventsEmitter  # noqa: F401
from .evaluation import (  # noqa: F401
    CompositeEvaluationEmitter,
    EvaluationEmitter,
    EvaluationEventsEmitter,
    EvaluationMetricsEmitter,
    EvaluationSpansEmitter,
)
from .metrics import MetricsEmitter  # noqa: F401
from .span import SpanEmitter  # noqa: F401
from .traceloop_compat import TraceloopCompatEmitter  # noqa: F401

__all__ = [
    "SpanEmitter",
    "MetricsEmitter",
    "ContentEventsEmitter",
    "TraceloopCompatEmitter",
    "CompositeGenerator",
    "EvaluationMetricsEmitter",
    "EvaluationEventsEmitter",
    "EvaluationSpansEmitter",
    "CompositeEvaluationEmitter",
    "EvaluationEmitter",
]
