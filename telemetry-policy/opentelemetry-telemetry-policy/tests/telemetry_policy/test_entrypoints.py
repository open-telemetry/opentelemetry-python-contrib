# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from importlib.metadata import entry_points
from pathlib import Path
from typing import Generator

import pytest

from opentelemetry._telemetry_policy import (
    PolicyStore,
    TraceSamplingPolicyImplementer,
    _entrypoints,
)
from opentelemetry._telemetry_policy.environment_variables import (
    OTEL_PYTHON_EXPERIMENTAL_OPAMP_IDENTIFYING_ATTRIBUTES,
    OTEL_PYTHON_EXPERIMENTAL_TELEMETRY_POLICY_FILE,
    OTEL_PYTHON_EXPERIMENTAL_TELEMETRY_POLICY_FILE_POLL_INTERVAL,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.sampling import Sampler


@pytest.fixture(autouse=True)
def _reset_entrypoints_state() -> Generator[None, None, None]:
    yield
    # Tear down the process-wide engine between tests
    with _entrypoints._lock:
        for provider in _entrypoints._providers:
            provider.shutdown(timeout=5.0)
        _entrypoints._providers.clear()
        _entrypoints._providers_started = False
        _entrypoints._trace_implementer = TraceSamplingPolicyImplementer()
        _entrypoints._store = PolicyStore()
        _entrypoints._store.add_implementer(_entrypoints._trace_implementer)


def _sampled(sampler: Sampler, attributes: dict[str, str]) -> bool:
    tracer = TracerProvider(sampler=sampler).get_tracer("test")
    span = tracer.start_span("span", attributes=attributes)
    span.end()
    return span.get_span_context().trace_flags.sampled


def _policy_document(percentage: float) -> str:
    return json.dumps(
        {
            "policies": [
                {
                    "id": "sample-database-spans",
                    "name": "Sample database spans",
                    "trace": {
                        "match": [{"span_attribute": ["db.system"], "exists": True}],
                        "keep": {"percentage": percentage},
                    },
                }
            ]
        }
    )


def test_sampler_entry_point_registered() -> None:
    (entry_point,) = entry_points(group="opentelemetry_traces_sampler", name="telemetry_policy")

    factory = entry_point.load()

    assert factory is _entrypoints.traces_sampler_factory
    assert isinstance(factory(None), Sampler)


def test_opamp_entry_point_registered() -> None:
    (entry_point,) = entry_points(group="_opentelemetry_opamp", name="post_sdk_init_function")

    assert entry_point.load() is _entrypoints.post_sdk_init


def test_factory_returns_singleton_sampler() -> None:
    assert _entrypoints.traces_sampler_factory(None) is _entrypoints.traces_sampler_factory(None)


def test_factory_arg_sets_fallback_probability() -> None:
    assert _sampled(_entrypoints.traces_sampler_factory("0"), {"http.route": "/"}) is False


def test_factory_arg_updates_existing_sampler() -> None:
    sampler = _entrypoints.traces_sampler_factory(None)
    assert _sampled(sampler, {"http.route": "/"}) is True

    assert _entrypoints.traces_sampler_factory("0") is sampler
    assert _sampled(sampler, {"http.route": "/"}) is False


def test_factory_invalid_arg_uses_default_fallback() -> None:
    assert _sampled(_entrypoints.traces_sampler_factory("nope"), {"http.route": "/"}) is True


def test_post_sdk_init_without_config_is_noop() -> None:
    _entrypoints.post_sdk_init(Resource.create({}))

    assert not _entrypoints._providers  # pylint: disable=protected-access


def test_post_sdk_init_starts_file_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "policies.json"
    path.write_text(_policy_document(0.0))
    monkeypatch.setenv(OTEL_PYTHON_EXPERIMENTAL_TELEMETRY_POLICY_FILE, str(path))
    monkeypatch.setenv(OTEL_PYTHON_EXPERIMENTAL_TELEMETRY_POLICY_FILE_POLL_INTERVAL, "0")
    sampler = _entrypoints.traces_sampler_factory(None)

    _entrypoints.post_sdk_init(Resource.create({}))

    assert _sampled(sampler, {"db.system": "postgresql"}) is False
    assert _sampled(sampler, {"http.route": "/"}) is True

    # A repeated call must not start duplicate providers.
    _entrypoints.post_sdk_init(Resource.create({}))
    assert len(_entrypoints._providers) == 1  # pylint: disable=protected-access


def test_resource_attribute_split() -> None:
    resource = Resource.create(
        {
            "service.name": "svc",
            "service.instance.id": "instance-1",
            "deployment.environment.name": "prod",
        }
    )

    identifying = _entrypoints._identifying_attributes(resource)  # pylint: disable=protected-access
    non_identifying = _entrypoints._non_identifying_attributes(resource)  # pylint: disable=protected-access

    assert identifying["service.name"] == "svc"
    assert identifying["service.instance.id"] == "instance-1"
    assert "service.name" not in non_identifying
    assert non_identifying["deployment.environment.name"] == "prod"


def test_identifying_attributes_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    resource = Resource.create(
        {
            "service.name": "svc",
            "service.instance.id": "instance-1",
            "deployment.environment.name": "prod",
        }
    )
    monkeypatch.setenv(
        OTEL_PYTHON_EXPERIMENTAL_OPAMP_IDENTIFYING_ATTRIBUTES,
        "service.name, deployment.environment.name",
    )

    identifying = _entrypoints._identifying_attributes(resource)  # pylint: disable=protected-access
    non_identifying = _entrypoints._non_identifying_attributes(resource)  # pylint: disable=protected-access

    assert identifying == {"service.name": "svc", "deployment.environment.name": "prod"}
    # A key outside the configured set is non-identifying, even a service one.
    assert non_identifying["service.instance.id"] == "instance-1"
    assert "deployment.environment.name" not in non_identifying


def test_blank_identifying_attributes_uses_default(monkeypatch: pytest.MonkeyPatch) -> None:
    resource = Resource.create({"service.name": "svc"})
    monkeypatch.setenv(OTEL_PYTHON_EXPERIMENTAL_OPAMP_IDENTIFYING_ATTRIBUTES, " , ")

    identifying = _entrypoints._identifying_attributes(resource)  # pylint: disable=protected-access

    assert identifying["service.name"] == "svc"
