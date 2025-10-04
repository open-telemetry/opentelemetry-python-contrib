import os
from dataclasses import dataclass

from .environment_variables import (
    # OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT,
    OTEL_INSTRUMENTATION_GENAI_EMITTERS,
    OTEL_INSTRUMENTATION_GENAI_EVALUATION_ENABLE,
    OTEL_INSTRUMENTATION_GENAI_EVALUATION_INTERVAL,
    OTEL_INSTRUMENTATION_GENAI_EVALUATION_MAX_PER_MINUTE,
    OTEL_INSTRUMENTATION_GENAI_EVALUATION_SPAN_MODE,
    OTEL_INSTRUMENTATION_GENAI_EVALUATION_TARGETS,
    OTEL_INSTRUMENTATION_GENAI_EVALUATORS,
)
from .types import ContentCapturingMode
from .utils import get_content_capturing_mode


@dataclass(frozen=True)
class Settings:
    """
    Configuration for GenAI telemetry based on environment variables.
    """

    generator_kind: str
    evaluation_enabled: bool
    evaluation_evaluators: list[str]
    capture_content_span: bool
    capture_content_events: bool
    # New fields for multi-token emitter selection
    extra_emitters: list[str]
    only_traceloop_compat: bool
    raw_tokens: list[str]
    evaluation_span_mode: str
    evaluation_interval: float
    evaluation_max_per_minute: int
    evaluation_targets: list[str]  # normalized list (e.g. ["llm", "agent"])


def parse_env() -> Settings:
    """
    Parse relevant environment variables into a Settings object.

    Supports comma-separated OTEL_INSTRUMENTATION_GENAI_EMITTERS allowing extra emitters
    (e.g. "span,traceloop_compat"). Baseline values control the core span/metric/event set.
    """
    raw_val = os.environ.get(OTEL_INSTRUMENTATION_GENAI_EMITTERS, "span")
    tokens = [t.strip().lower() for t in raw_val.split(",") if t.strip()]
    if not tokens:
        tokens = ["span"]
    baseline_candidates = {"span", "span_metric", "span_metric_event"}
    baseline = next((t for t in tokens if t in baseline_candidates), None)
    extra_emitters: list[str] = []
    if baseline is None:
        # No baseline provided. If traceloop_compat only, treat specially.
        if tokens == ["traceloop_compat"]:
            baseline = "span"  # placeholder baseline but we'll suppress later
            extra_emitters = ["traceloop_compat"]
            only_traceloop = True
        else:
            # Fallback to span and keep the others as extras
            baseline = "span"
            extra_emitters = [
                t for t in tokens if t not in baseline_candidates
            ]
            only_traceloop = False
    else:
        extra_emitters = [t for t in tokens if t != baseline]
        only_traceloop = tokens == [
            "traceloop_compat"
        ]  # True only if sole token

    # Content capturing mode (span vs event vs both)
    try:
        mode = get_content_capturing_mode()
    except Exception:
        mode = ContentCapturingMode.NO_CONTENT

    if baseline == "span_metric_event":
        capture_content_events = mode in (
            ContentCapturingMode.EVENT_ONLY,
            ContentCapturingMode.SPAN_AND_EVENT,
        )
        # Capture in spans when mode is SPAN_ONLY or SPAN_AND_EVENT
        capture_content_span = mode in (
            ContentCapturingMode.SPAN_ONLY,
            ContentCapturingMode.SPAN_AND_EVENT,
        )
    else:
        capture_content_events = False
        capture_content_span = mode in (
            ContentCapturingMode.SPAN_ONLY,
            ContentCapturingMode.SPAN_AND_EVENT,
        )

    # Inline evaluation span mode normalization (avoid lambda call for lint compliance)
    raw_eval_span_mode = (
        os.environ.get(OTEL_INSTRUMENTATION_GENAI_EVALUATION_SPAN_MODE, "off")
        .strip()
        .lower()
    )
    normalized_eval_span_mode = (
        raw_eval_span_mode
        if raw_eval_span_mode in ("off", "aggregated", "per_metric")
        else "off"
    )

    # Evaluation targets (llm by default). Accepts comma separated values.
    raw_targets = os.environ.get(
        OTEL_INSTRUMENTATION_GENAI_EVALUATION_TARGETS, "llm"
    )
    evaluation_targets = []
    seen = set()
    for tok in raw_targets.split(","):
        val = tok.strip().lower()
        if not val:
            continue
        if val not in ("llm", "agent"):
            continue  # ignore unsupported future tokens silently
        if val in seen:
            continue
        seen.add(val)
        evaluation_targets.append(val)
    if not evaluation_targets:
        evaluation_targets = ["llm"]  # fallback

    return Settings(
        generator_kind=baseline,
        capture_content_span=capture_content_span,
        capture_content_events=capture_content_events,
        evaluation_enabled=(
            os.environ.get(
                OTEL_INSTRUMENTATION_GENAI_EVALUATION_ENABLE, "false"
            )
            .strip()
            .lower()
            in ("true", "1", "yes")
        ),
        evaluation_evaluators=[
            n.strip()
            for n in os.environ.get(
                OTEL_INSTRUMENTATION_GENAI_EVALUATORS,
                "",  # noqa: PLC3002
            ).split(",")
            if n.strip()
        ],
        extra_emitters=extra_emitters,
        only_traceloop_compat=only_traceloop,
        raw_tokens=tokens,
        evaluation_span_mode=normalized_eval_span_mode,
        evaluation_interval=float(
            os.environ.get(
                OTEL_INSTRUMENTATION_GENAI_EVALUATION_INTERVAL, "5.0"
            ).strip()
            or 5.0
        ),
        evaluation_max_per_minute=int(
            os.environ.get(
                OTEL_INSTRUMENTATION_GENAI_EVALUATION_MAX_PER_MINUTE, "0"
            ).strip()
            or 0
        ),
        evaluation_targets=evaluation_targets,
    )
