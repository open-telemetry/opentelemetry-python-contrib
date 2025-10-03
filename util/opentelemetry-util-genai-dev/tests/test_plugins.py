from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable
from unittest.mock import patch

import pytest

from opentelemetry.util.genai.environment_variables import (
    OTEL_INSTRUMENTATION_GENAI_EMITTERS,
)
from opentelemetry.util.genai.handler import get_telemetry_handler
from opentelemetry.util.genai.plugins import (
    PluginEmitterBundle,
    load_emitter_plugin,
)


@dataclass
class _FakeEntryPoint:
    name: str
    loader: Callable[..., Any]

    def load(self) -> Callable[..., Any]:
        return self.loader


class _SentinelEmitter:
    def __init__(self) -> None:
        self.role = "sentinel"

    def start(
        self, obj: Any
    ) -> None:  # pragma: no cover - behaviour tested via inclusion
        return None

    def finish(
        self, obj: Any
    ) -> None:  # pragma: no cover - behaviour tested via inclusion
        return None

    def error(
        self, error: Any, obj: Any
    ) -> None:  # pragma: no cover - behaviour tested via inclusion
        return None


def _bundle_factory(**_: Any) -> PluginEmitterBundle:
    return PluginEmitterBundle(
        emitters=[_SentinelEmitter()],
        replace_default_emitters=True,
    )


def test_load_emitter_plugin_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "opentelemetry.util.genai.plugins.entry_points",
        lambda group: [_FakeEntryPoint("splunk", _bundle_factory)]
        if group == "opentelemetry_genai_emitters"
        else [],
    )

    bundle = load_emitter_plugin(
        "splunk",
        tracer=None,
        meter=None,
        event_logger=None,
        settings=object(),
    )
    assert bundle is not None
    assert bundle.replace_default_emitters is True
    assert len(bundle.emitters) == 1


def test_handler_uses_plugin_emitters(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "opentelemetry.util.genai.plugins.entry_points",
        lambda group: [_FakeEntryPoint("splunk", _bundle_factory)]
        if group == "opentelemetry_genai_emitters"
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

    generators = handler._generator._generators  # type: ignore[attr-defined]
    assert len(generators) == 1
    assert isinstance(generators[0], _SentinelEmitter)
    handler._evaluation_manager.shutdown()
