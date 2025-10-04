from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable
from unittest.mock import patch

import pytest

from opentelemetry.util.genai.emitters.spec import EmitterSpec
from opentelemetry.util.genai.environment_variables import (
    OTEL_INSTRUMENTATION_GENAI_EMITTERS,
)
from opentelemetry.util.genai.handler import get_telemetry_handler
from opentelemetry.util.genai.plugins import load_emitter_specs


@dataclass
class _FakeEntryPoint:
    name: str
    loader: Callable[..., Any]

    def load(self) -> Callable[..., Any]:
        return self.loader


class _SentinelEmitter:
    def __init__(self) -> None:
        self.role = "sentinel"

    def on_start(
        self, obj: Any
    ) -> None:  # pragma: no cover - behaviour tested via inclusion
        return None

    def on_end(
        self, obj: Any
    ) -> None:  # pragma: no cover - behaviour tested via inclusion
        return None

    def on_error(
        self, error: Any, obj: Any
    ) -> None:  # pragma: no cover - behaviour tested via inclusion
        return None

    def on_evaluation_results(
        self, results: Any, obj: Any | None = None
    ) -> None:  # pragma: no cover - default no-op
        return None


def _spec_factory(**_: Any) -> list[EmitterSpec]:
    return [
        EmitterSpec(
            name="SentinelEmitter",
            category="span",
            mode="replace-category",
            factory=lambda ctx: _SentinelEmitter(),
        )
    ]


def test_load_emitter_specs_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "opentelemetry.util.genai.plugins.entry_points",
        lambda **kwargs: [_FakeEntryPoint("splunk", _spec_factory)]
        if kwargs.get("group") == "opentelemetry_util_genai_emitters"
        else [],
    )

    import opentelemetry.util.genai.plugins as plugins

    calls: list[object] = []

    def _wrapped(provider, source, *, _orig=plugins._coerce_to_specs):
        calls.append(provider)
        return _orig(provider, source)

    monkeypatch.setattr(plugins, "_coerce_to_specs", _wrapped)

    specs = load_emitter_specs(["splunk"])
    assert calls, "_coerce_to_specs was not invoked"
    assert len(specs) == 1
    assert specs[0].name == "SentinelEmitter"


def test_handler_uses_plugin_emitters(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "opentelemetry.util.genai.plugins.entry_points",
        lambda **kwargs: [_FakeEntryPoint("splunk", _spec_factory)]
        if kwargs.get("group") == "opentelemetry_util_genai_emitters"
        else [],
    )

    with patch.dict(
        os.environ,
        {OTEL_INSTRUMENTATION_GENAI_EMITTERS: "splunk"},
        clear=True,
    ):
        if hasattr(get_telemetry_handler, "_default_handler"):
            delattr(get_telemetry_handler, "_default_handler")
        handler = get_telemetry_handler()

    span_emitters = list(handler._emitter.emitters_for("span"))  # type: ignore[attr-defined]
    assert len(span_emitters) == 1
    assert isinstance(span_emitters[0], _SentinelEmitter)
    if hasattr(handler._evaluation_manager, "shutdown"):
        handler._evaluation_manager.shutdown()
    if hasattr(get_telemetry_handler, "_default_handler"):
        delattr(get_telemetry_handler, "_default_handler")
