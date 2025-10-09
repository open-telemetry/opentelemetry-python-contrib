from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Dict

from .emitters.spec import CategoryOverride
from .environment_variables import (
    OTEL_GENAI_EVALUATION_EVENT_LEGACY,
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT,
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGES,
    OTEL_INSTRUMENTATION_GENAI_EMITTERS,
    OTEL_INSTRUMENTATION_GENAI_EMITTERS_CONTENT_EVENTS,
    OTEL_INSTRUMENTATION_GENAI_EMITTERS_EVALUATION,
    OTEL_INSTRUMENTATION_GENAI_EMITTERS_METRICS,
    OTEL_INSTRUMENTATION_GENAI_EMITTERS_SPAN,
)
from .types import ContentCapturingMode
from .utils import get_content_capturing_mode

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Settings:
    """Configuration for GenAI emitters derived from environment variables."""

    enable_span: bool
    enable_metrics: bool
    enable_content_events: bool
    extra_emitters: list[str]
    only_traceloop_compat: bool
    raw_tokens: list[str]
    capture_messages_mode: ContentCapturingMode
    capture_messages_override: bool
    legacy_capture_request: bool
    emit_legacy_evaluation_event: bool
    category_overrides: Dict[str, CategoryOverride]


def parse_env() -> Settings:
    """Parse emitter-related environment variables into structured settings."""

    raw_val = os.environ.get(OTEL_INSTRUMENTATION_GENAI_EMITTERS, "span")
    tokens = [
        token.strip().lower() for token in raw_val.split(",") if token.strip()
    ]
    if not tokens:
        tokens = ["span"]

    baseline_map = {
        "span": (True, False, False),
        "span_metric": (True, True, False),
        "span_metric_event": (True, True, True),
    }

    baseline = next((token for token in tokens if token in baseline_map), None)
    extra_emitters: list[str] = []
    only_traceloop_compat = False

    if baseline is None:
        if tokens == ["traceloop_compat"]:
            baseline = "span"
            extra_emitters = ["traceloop_compat"]
            only_traceloop_compat = True
        else:
            baseline = "span"
            extra_emitters = [
                token for token in tokens if token not in baseline_map
            ]
    else:
        extra_emitters = [token for token in tokens if token != baseline]

    enable_span, enable_metrics, enable_content_events = baseline_map.get(
        baseline, (True, False, False)
    )

    capture_messages_override = bool(
        os.environ.get(OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGES)
    )
    capture_mode = get_content_capturing_mode()

    # Legacy compat flag retained for handler refresh to honour previous
    # message capture overrides tied to CAPTURE_MESSAGE_CONTENT
    legacy_flag = os.environ.get(
        OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, ""
    ).strip()
    legacy_capture_request = legacy_flag.lower() in {"true", "1", "yes"}

    overrides: Dict[str, CategoryOverride] = {}
    override_env_map = {
        "span": os.environ.get(OTEL_INSTRUMENTATION_GENAI_EMITTERS_SPAN, ""),
        "metrics": os.environ.get(
            OTEL_INSTRUMENTATION_GENAI_EMITTERS_METRICS, ""
        ),
        "content_events": os.environ.get(
            OTEL_INSTRUMENTATION_GENAI_EMITTERS_CONTENT_EVENTS, ""
        ),
        "evaluation": os.environ.get(
            OTEL_INSTRUMENTATION_GENAI_EMITTERS_EVALUATION, ""
        ),
    }
    for category, raw in override_env_map.items():
        override = _parse_category_override(category, raw)
        if override is not None:
            overrides[category] = override

    legacy_event_flag = os.environ.get(
        OTEL_GENAI_EVALUATION_EVENT_LEGACY, ""
    ).strip()
    emit_legacy_event = legacy_event_flag.lower() in {"1", "true", "yes"}

    return Settings(
        enable_span=enable_span,
        enable_metrics=enable_metrics,
        enable_content_events=enable_content_events,
        extra_emitters=extra_emitters,
        only_traceloop_compat=only_traceloop_compat,
        raw_tokens=tokens,
        capture_messages_mode=capture_mode,
        capture_messages_override=capture_messages_override,
        legacy_capture_request=legacy_capture_request,
        emit_legacy_evaluation_event=emit_legacy_event,
        category_overrides=overrides,
    )


def _parse_category_override(
    category: str, raw: str
) -> CategoryOverride | None:  # pragma: no cover - thin parsing
    if not raw:
        return None
    text = raw.strip()
    if not text:
        return None
    directive = None
    remainder = text
    if ":" in text:
        prefix, remainder = text.split(":", 1)
        directive = prefix.strip().lower()
    names = [name.strip() for name in remainder.split(",") if name.strip()]
    mode_map = {
        None: "append",
        "append": "append",
        "prepend": "prepend",
        "replace": "replace-category",
        "replace-category": "replace-category",
        "replace-same-name": "replace-same-name",
    }
    mode = mode_map.get(directive)
    if mode is None:
        if directive:
            _logger.warning(
                "Unknown emitter override directive '%s' for category '%s'",
                directive,
                category,
            )
        mode = "append"
    if mode != "replace-category" and not names:
        return None
    return CategoryOverride(mode=mode, emitter_names=tuple(names))


__all__ = ["Settings", "parse_env"]
