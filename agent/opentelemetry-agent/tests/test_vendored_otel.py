# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Checks of the vendored OpenTelemetry packages and the patches that make them work under the agent's namespace."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from opentelemetry.agent._vendor.opentelemetry.configuration._exceptions import ConfigurationError
from opentelemetry.agent._vendor.opentelemetry.configuration.file._loader import load_config_file
from opentelemetry.agent._vendor.opentelemetry.distro import OpenTelemetryDistro
from opentelemetry.agent._vendor.opentelemetry.environment_variables import OTEL_TRACES_EXPORTER
from opentelemetry.agent._vendor.opentelemetry.sdk._configuration import _get_exporter_names, _import_exporters
from opentelemetry.agent._vendor.opentelemetry.sdk.environment_variables import OTEL_EXPORTER_OTLP_PROTOCOL
from opentelemetry.agent._vendor.opentelemetry.sdk.trace import TracerProvider
from opentelemetry.agent._vendor.opentelemetry.sdk.util.instrumentation import InstrumentationScope
from opentelemetry.agent._vendor.opentelemetry.util._importlib_metadata import distributions, entry_points

NAMESPACE = "opentelemetry.agent._vendor"


def test_entry_points_are_vendored() -> None:
    eps = entry_points()

    assert eps
    assert all(entry_point.module.startswith(f"{NAMESPACE}.") for entry_point in eps)
    assert {dist.metadata["Name"] for dist in distributions()} >= {"opentelemetry-sdk", "opentelemetry-distro"}


def test_instrumentor_entry_point_has_dist_requires() -> None:
    [entry_point] = entry_points(group="opentelemetry_instrumentor")

    assert entry_point.name == "aiohttp-client"
    assert entry_point.value == f"{NAMESPACE}.opentelemetry.instrumentation.aiohttp_client:AioHttpClientInstrumentor"
    assert entry_point.dist is not None
    # The dependency check of auto-instrumentation reads the "instruments" extra.
    assert any(
        "extra ==" in requirement and "aiohttp" in requirement for requirement in entry_point.dist.requires or []
    )


def test_otlp_exporter_defaults_to_http(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(OTEL_TRACES_EXPORTER, "otlp")
    monkeypatch.delenv(OTEL_EXPORTER_OTLP_PROTOCOL, raising=False)

    OpenTelemetryDistro().configure()
    names = _get_exporter_names("traces")
    trace_exporters, _, _ = _import_exporters(names, [], [])

    assert os.environ[OTEL_EXPORTER_OTLP_PROTOCOL] == "http/protobuf"
    assert names == ["otlp_proto_http"]
    assert trace_exporters["otlp_proto_http"].__module__ == (
        f"{NAMESPACE}.opentelemetry.exporter.otlp.proto.http.trace_exporter"
    )


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        pytest.param(
            f"{NAMESPACE}.opentelemetry.instrumentation.aiohttp_client",
            "opentelemetry.instrumentation.aiohttp_client",
            id="vendored",
        ),
        pytest.param("my.app", "my.app", id="application"),
    ],
)
def test_instrumentation_scope_name(name: str, expected: str) -> None:
    tracer = TracerProvider().get_tracer(name)

    assert InstrumentationScope(name).name == expected
    assert tracer._instrumentation_scope.name == expected  # pylint: disable=protected-access


def test_load_config_file_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SERVICE", "checkout")
    config_file = tmp_path / "otel.yaml"
    config_file.write_text(
        'file_format: "1.0"\n'
        "disabled: off\n"  # a string in YAML 1.2, not a boolean
        "resource:\n"
        "  attributes:\n"
        "    - name: service.name\n"
        "      value: ${SERVICE}\n"
    )

    with pytest.raises(ConfigurationError, match=r"Configuration does not match schema: .*disabled.* must be boolean"):
        load_config_file(config_file)

    config_file.write_text(config_file.read_text().replace("disabled: off", "disabled: false"))
    config = load_config_file(config_file)

    assert config.disabled is False
    assert config.resource is not None and config.resource.attributes is not None
    [attribute] = config.resource.attributes
    assert (attribute.name, attribute.value) == ("service.name", "checkout")


def test_load_config_file_invalid_yaml(tmp_path: Path) -> None:
    config_file = tmp_path / "otel.yaml"
    config_file.write_text("file_format: [\n")

    with pytest.raises(ConfigurationError, match="Failed to parse YAML"):
        load_config_file(config_file)


def test_imports_stay_in_namespace() -> None:
    # In a fresh interpreter: importing the vendored packages must not import the application's copies.
    modules = [
        "opentelemetry.sdk._configuration",
        "opentelemetry.distro",
        "opentelemetry.instrumentation.auto_instrumentation",
        "opentelemetry.configuration.file._loader",
        "opentelemetry.exporter.otlp.proto.http.trace_exporter",
        "opentelemetry.exporter.otlp.json.http.trace_exporter",
        "opentelemetry.exporter.otlp.json.file.trace_exporter",
        "opentelemetry.exporter.prometheus",
        "opentelemetry.propagators.b3",
    ]
    # Modules loaded at startup (e.g. by *-nspkg.pth files of the environment) don't count.
    code = (
        "import json, sys\n"
        "startup = set(sys.modules)\n"
        f"for module in {modules!r}:\n"
        f"    __import__({NAMESPACE!r} + '.' + module)\n"
        "print(json.dumps(sorted(set(sys.modules) - startup)))\n"
    )
    loaded = json.loads(subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True).stdout)

    vendored = {"google", "ruamel", "fastjsonschema", "wrapt", "packaging", "requests", "urllib3", "typing_extensions"}
    leaked = [
        module
        for module in loaded
        if module.split(".", 1)[0] in vendored
        or (
            module.startswith("opentelemetry.")
            and module not in ("opentelemetry.agent", NAMESPACE)
            and not module.startswith(f"{NAMESPACE}.")
        )
    ]
    assert leaked == []
