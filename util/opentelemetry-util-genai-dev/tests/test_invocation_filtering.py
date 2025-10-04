from __future__ import annotations

from typing import List

import pytest

from opentelemetry.util.genai.config import Settings
from opentelemetry.util.genai.emitters.configuration import (
    build_emitter_pipeline,
)
from opentelemetry.util.genai.emitters.spec import (
    EmitterFactoryContext,
    EmitterSpec,
)
from opentelemetry.util.genai.interfaces import EmitterMeta
from opentelemetry.util.genai.types import (
    AgentInvocation,
    ContentCapturingMode,
    LLMInvocation,
)


class _RecordingEmitter(EmitterMeta):
    role = "span"
    name = "recording_span"

    def __init__(self) -> None:
        self.started: List[str] = []

    def on_start(self, obj: object) -> None:
        self.started.append(type(obj).__name__)


@pytest.fixture
def _settings() -> Settings:
    return Settings(
        enable_span=True,
        enable_metrics=False,
        enable_content_events=False,
        extra_emitters=["recording"],
        only_traceloop_compat=False,
        raw_tokens=["span", "recording"],
        capture_messages_mode=ContentCapturingMode.SPAN_ONLY,
        capture_messages_override=False,
        legacy_capture_request=False,
        category_overrides={},
    )


def test_invocation_type_filter(monkeypatch, _settings):
    captured: List[_RecordingEmitter] = []

    def _factory(ctx: EmitterFactoryContext) -> _RecordingEmitter:
        emitter = _RecordingEmitter()
        captured.append(emitter)
        return emitter

    def _fake_load(extra_emitters: List[str]):
        if "recording" in extra_emitters:
            return [
                EmitterSpec(
                    name="RecordingSpan",
                    category="span",
                    factory=_factory,
                    invocation_types=("LLMInvocation",),
                )
            ]
        return []

    monkeypatch.setattr(
        "opentelemetry.util.genai.emitters.configuration.load_emitter_specs",
        _fake_load,
    )

    composite, _ = build_emitter_pipeline(
        tracer=None,
        meter=None,
        event_logger=None,
        content_logger=None,
        evaluation_histogram=None,
        settings=_settings,
    )

    assert captured, "Recording emitter should be instantiated"
    emitter = captured[0]

    composite.on_start(LLMInvocation(request_model="demo"))
    composite.on_start(AgentInvocation(name="worker", operation="invoke"))

    assert emitter.started == ["LLMInvocation"]
