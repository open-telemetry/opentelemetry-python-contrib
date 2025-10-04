"""Emitter package consolidating all telemetry signal emitters."""

from __future__ import annotations

from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)

from .composite import CompositeEmitter  # noqa: F401
from .content_events import ContentEventsEmitter  # noqa: F401
from .evaluation import (  # noqa: F401
    EvaluationEventsEmitter,
    EvaluationMetricsEmitter,
)
from .metrics import MetricsEmitter  # noqa: F401
from .span import SpanEmitter  # noqa: F401

__all__ = [
    "SpanEmitter",
    "MetricsEmitter",
    "ContentEventsEmitter",
    "CompositeEmitter",
    "EvaluationMetricsEmitter",
    "EvaluationEventsEmitter",
]
