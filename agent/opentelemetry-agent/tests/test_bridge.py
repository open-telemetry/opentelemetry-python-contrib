# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""The bridge from the application's opentelemetry-api (installed in the test environment) to the vendored SDK.

The application's API selects the bridge through environment variables when it's imported, and keeps global
state: each test runs a script in a new interpreter. Its spans are exported in memory by the vendored SDK and
printed as JSON.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest

from opentelemetry.agent._vendor.opentelemetry.environment_variables import (
    _AGENT_BRIDGE,
    OTEL_PYTHON_CONTEXT,
    OTEL_PYTHON_TRACER_PROVIDER,
)

_BRIDGE_ENVIRONMENT = {OTEL_PYTHON_CONTEXT: _AGENT_BRIDGE, OTEL_PYTHON_TRACER_PROVIDER: _AGENT_BRIDGE}

_PRELUDE = """
import json

from opentelemetry.agent._vendor.opentelemetry import trace as agent_trace
from opentelemetry.agent._vendor.opentelemetry.sdk.trace import TracerProvider
from opentelemetry.agent._vendor.opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.agent._vendor.opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

exporter = InMemorySpanExporter()
agent_provider = TracerProvider()
agent_provider.add_span_processor(SimpleSpanProcessor(exporter))
agent_trace.set_tracer_provider(agent_provider)
results = {}
"""

_EPILOGUE = """
results["spans"] = [
    {
        "name": span.name,
        "kind": span.kind.name,
        "trace_id": span.context.trace_id,
        "span_id": span.context.span_id,
        "parent_id": span.parent.span_id if span.parent else None,
        "status": [span.status.status_code.name, span.status.description],
        "attributes": dict(span.attributes),
        "events": [[event.name, dict(event.attributes)] for event in span.events],
        "links": [[link.context.span_id, dict(link.attributes)] for link in span.links],
    }
    for span in exporter.get_finished_spans()
]
print(json.dumps(results))
"""


def _run(script: str, environment: dict[str, str] | None = None, prelude: bool = True) -> Any:
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in (OTEL_PYTHON_CONTEXT, OTEL_PYTHON_TRACER_PROVIDER, "PYTHONPATH")
    }
    env |= _BRIDGE_ENVIRONMENT if environment is None else environment
    source = textwrap.dedent(script)
    if prelude:
        source = _PRELUDE + source + _EPILOGUE
    result = subprocess.run(
        [sys.executable, "-c", source], env=env, capture_output=True, text=True, check=False, timeout=60
    )
    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr, result.stderr
    return json.loads(result.stdout.splitlines()[-1])


def _spans_by_name(results: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {span["name"]: span for span in results["spans"]}


def test_app_spans_are_exported_by_the_vendored_sdk() -> None:
    results = _run(
        """
        from opentelemetry import trace

        results["provider"] = type(trace.get_tracer_provider()).__name__
        tracer = trace.get_tracer("app")
        with tracer.start_as_current_span("parent", kind=trace.SpanKind.SERVER, attributes={"a": 1}) as parent:
            results["is_app_span"] = isinstance(trace.get_current_span(), trace.Span)
            results["current_is_parent"] = trace.get_current_span() == parent
            with tracer.start_as_current_span("child", links=[trace.Link(parent.get_span_context(), {"l": "v"})]) as child:
                child.set_attribute("b", "x")
                child.add_event("event", {"c": 2.5})
                child.set_status(trace.Status(trace.StatusCode.ERROR, "failed"))
        span = tracer.start_span("status-code")
        span.set_status(trace.StatusCode.OK)
        span.end()
        """
    )

    spans = _spans_by_name(results)
    assert results["provider"] == "BridgeTracerProvider"
    assert results["is_app_span"] is True
    assert results["current_is_parent"] is True
    parent, child = spans["parent"], spans["child"]
    assert parent["kind"] == "SERVER"
    assert parent["parent_id"] is None
    assert parent["attributes"] == {"a": 1}
    assert child["kind"] == "INTERNAL"
    assert child["trace_id"] == parent["trace_id"]
    assert child["parent_id"] == parent["span_id"]
    assert child["attributes"] == {"b": "x"}
    assert child["events"] == [["event", {"c": 2.5}]]
    assert child["links"] == [[parent["span_id"], {"l": "v"}]]
    assert child["status"] == ["ERROR", "failed"]
    assert spans["status-code"]["status"] == ["OK", None]


def test_exception_in_app_span() -> None:
    results = _run(
        """
        from opentelemetry import trace

        tracer = trace.get_tracer("app")
        try:
            with tracer.start_as_current_span("failing"):
                raise ValueError("boom")
        except ValueError:
            pass
        try:
            with tracer.start_span("failing-span"):
                raise KeyError("key")
        except KeyError:
            pass
        """
    )

    spans = _spans_by_name(results)
    for name, description in (("failing", "ValueError: boom"), ("failing-span", "KeyError: 'key'")):
        assert spans[name]["status"] == ["ERROR", description]
        [(event_name, attributes)] = spans[name]["events"]
        assert event_name == "exception"
        assert attributes["exception.type"] in ("ValueError", "KeyError")


def test_vendored_and_app_spans_parent_each_other() -> None:
    results = _run(
        """
        from opentelemetry import trace

        tracer = trace.get_tracer("app")
        agent_tracer = agent_trace.get_tracer("instrumentation")
        with tracer.start_as_current_span("app-outer"):
            results["agent_current"] = agent_trace.get_current_span().name
            with agent_tracer.start_as_current_span("instrumentation"):
                with tracer.start_as_current_span("app-inner"):
                    pass
        """
    )

    spans = _spans_by_name(results)
    assert results["agent_current"] == "app-outer"
    assert spans["instrumentation"]["parent_id"] == spans["app-outer"]["span_id"]
    assert spans["app-inner"]["parent_id"] == spans["instrumentation"]["span_id"]


def test_explicit_parent_context() -> None:
    results = _run(
        """
        from opentelemetry import trace

        tracer = trace.get_tracer("app")
        root = tracer.start_span("root")
        child = tracer.start_span("child", context=trace.set_span_in_context(root))
        child.end()
        root.end()
        orphan = tracer.start_span("orphan", context=trace.set_span_in_context(trace.INVALID_SPAN))
        orphan.end()
        """
    )

    spans = _spans_by_name(results)
    assert spans["child"]["parent_id"] == spans["root"]["span_id"]
    assert spans["orphan"]["parent_id"] is None


def test_app_propagators_use_bridged_spans() -> None:
    trace_id = 0x0AF7651916CD43DD8448EB211C80319C
    results = _run(
        """
        from opentelemetry import propagate, trace

        tracer = trace.get_tracer("app")
        context = propagate.extract({"traceparent": "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"})
        with tracer.start_as_current_span("remote-child", context=context) as span:
            carrier = {}
            propagate.inject(carrier)
            results["traceparent"] = carrier["traceparent"]
            results["span_id"] = span.get_span_context().span_id
        """
    )

    [span] = results["spans"]
    assert span["trace_id"] == trace_id
    assert span["parent_id"] == 0xB7AD6B7169203331
    assert results["traceparent"].startswith(f"00-{trace_id:032x}-{results['span_id']:016x}-")


def test_extracted_span_round_trips() -> None:
    results = _run(
        """
        from opentelemetry import context, propagate, trace

        extracted = trace.get_current_span(propagate.extract({"traceparent": "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"}))
        token = context.attach(trace.set_span_in_context(extracted))
        results["same_span"] = trace.get_current_span() is extracted
        context.detach(token)
        results["detached"] = trace.get_current_span() is trace.INVALID_SPAN
        """
    )

    assert results["same_span"] is True
    assert results["detached"] is True


def test_baggage_and_suppression_are_shared() -> None:
    results = _run(
        """
        from opentelemetry import baggage, context
        from opentelemetry.agent._vendor.opentelemetry import baggage as agent_baggage
        from opentelemetry.agent._vendor.opentelemetry import context as agent_context
        from opentelemetry.agent._vendor.opentelemetry.instrumentation.utils import is_instrumentation_enabled

        token = context.attach(baggage.set_baggage("app", "1"))
        results["agent_baggage"] = agent_baggage.get_baggage("app")
        agent_token = agent_context.attach(agent_baggage.set_baggage("agent", "2"))
        results["app_baggage"] = dict(baggage.get_all())
        agent_context.detach(agent_token)
        context.detach(token)

        token = context.attach(context.set_value(context._SUPPRESS_INSTRUMENTATION_KEY, True))
        results["suppressed"] = not is_instrumentation_enabled()
        context.detach(token)
        results["enabled"] = is_instrumentation_enabled()
        """
    )

    assert results["agent_baggage"] == "1"
    assert results["app_baggage"] == {"app": "1", "agent": "2"}
    assert results["suppressed"] is True
    assert results["enabled"] is True


def test_app_provider_set_first_is_kept() -> None:
    results = _run(
        """
        from opentelemetry import trace

        trace.set_tracer_provider(trace.NoOpTracerProvider())
        with trace.get_tracer("app").start_as_current_span("not-bridged"):
            pass
        results["provider"] = type(trace.get_tracer_provider()).__name__
        """
    )

    assert results["provider"] == "NoOpTracerProvider"
    assert results["spans"] == []


def test_environment_is_released_once_loaded() -> None:
    results = _run(
        f"""
        import os
        from opentelemetry import context, trace

        context.get_current()
        trace.get_tracer_provider()
        results["environment"] = [os.environ.get({OTEL_PYTHON_CONTEXT!r}), os.environ.get({OTEL_PYTHON_TRACER_PROVIDER!r})]
        """
    )

    assert results["environment"] == [None, None]


def test_vendored_api_ignores_the_bridge_selection() -> None:
    results = _run(
        """
        import json
        from opentelemetry.agent._vendor.opentelemetry import context, trace

        print(json.dumps({
            "runtime_context": type(context._RUNTIME_CONTEXT).__name__,
            "provider": type(trace.get_tracer_provider()).__name__,
        }))
        """,
        prelude=False,
    )

    assert results == {"runtime_context": "ContextVarsRuntimeContext", "provider": "ProxyTracerProvider"}


_SITECUSTOMIZE_DIR = (
    Path(__file__).parents[1] / "src/opentelemetry/agent/_vendor/opentelemetry/instrumentation/auto_instrumentation"
)


@pytest.mark.parametrize(
    ("environment", "expected"),
    [
        ({}, [_AGENT_BRIDGE, _AGENT_BRIDGE]),
        ({OTEL_PYTHON_CONTEXT: "contextvars_context"}, ["contextvars_context", _AGENT_BRIDGE]),
    ],
)
def test_sitecustomize_selects_the_bridge(environment: dict[str, str], expected: list[str]) -> None:
    results = _run(
        f"""
        import json, os

        print(json.dumps([os.environ.get({OTEL_PYTHON_CONTEXT!r}), os.environ.get({OTEL_PYTHON_TRACER_PROVIDER!r})]))
        """,
        environment={
            "PYTHONPATH": str(_SITECUSTOMIZE_DIR),
            "OTEL_TRACES_EXPORTER": "none",
            "OTEL_METRICS_EXPORTER": "none",
            "OTEL_LOGS_EXPORTER": "none",
        }
        | environment,
        prelude=False,
    )

    assert results == expected
