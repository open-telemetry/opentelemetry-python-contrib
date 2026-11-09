# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from importlib.metadata import distributions
from pathlib import Path

import pytest

from opentelemetry.vendor.entry_points import rewrite_entry_points, write_metadata
from opentelemetry.vendor.errors import VendorError
from opentelemetry.vendor.metadata import VendoredPackage

NAMESPACE = "opentelemetry.agent._vendor"
NAMES = frozenset({"opentelemetry", "wrapt"})


def _package(tmp_path: Path, entry_points: str | None) -> VendoredPackage:
    dist_info = tmp_path / "unpacked" / "opentelemetry_sdk-1.0.dist-info"
    dist_info.mkdir(parents=True)
    (dist_info / "METADATA").write_text(
        'Metadata-Version: 2.4\nName: opentelemetry-sdk\nVersion: 1.0\nRequires-Dist: wrapt; extra == "instruments"\n'
    )
    (dist_info / "RECORD").write_text("")
    if entry_points is not None:
        (dist_info / "entry_points.txt").write_text(entry_points)
    return VendoredPackage(
        name="opentelemetry-sdk",
        version="1.0",
        sha256="0" * 64,
        license_expression=None,
        top_level_names=("opentelemetry",),
        license_files={},
        dist_info=dist_info,
    )


def _vendored_tree(tmp_path: Path, *modules: str) -> Path:
    destination = tmp_path / "_vendor"
    for module in modules:
        path = destination / module
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("")
    return destination


def test_rewrite_entry_points() -> None:
    text = (
        "[console_scripts]\n"
        "opentelemetry-instrument = opentelemetry.instrumentation.auto_instrumentation:run\n"
        "\n"
        "[opentelemetry_traces_exporter]\n"
        "Console = opentelemetry.sdk.trace.export:ConsoleSpanExporter\n"
        "extras = opentelemetry.sdk.trace : Tracer [grpc]\n"
        "module-only = opentelemetry.sdk.environment_variables\n"
        "already = opentelemetry.agent._vendor.opentelemetry.sdk:X\n"
        "external = aiohttp.client:ClientSession\n"
        "\n"
        "[gui_scripts]\n"
        "gui = opentelemetry.gui:main\n"
    )

    assert rewrite_entry_points(text, NAMESPACE, NAMES) == {
        "opentelemetry_traces_exporter": {
            "Console": "opentelemetry.agent._vendor.opentelemetry.sdk.trace.export:ConsoleSpanExporter",
            "extras": "opentelemetry.agent._vendor.opentelemetry.sdk.trace : Tracer [grpc]",
            "module-only": "opentelemetry.agent._vendor.opentelemetry.sdk.environment_variables",
            "already": "opentelemetry.agent._vendor.opentelemetry.sdk:X",
            "external": "aiohttp.client:ClientSession",
        }
    }


def test_rewrite_entry_points_invalid_value() -> None:
    with pytest.raises(VendorError, match=r"invalid entry point group:name = 'not a module'"):
        rewrite_entry_points("[group]\nname = not a module\n", NAMESPACE, NAMES)


def test_write_metadata(tmp_path: Path) -> None:
    destination = _vendored_tree(
        tmp_path, "opentelemetry/sdk/trace/export/__init__.py", "opentelemetry/sdk/environment_variables.py"
    )
    package = _package(
        tmp_path,
        "[console_scripts]\nscript = opentelemetry.sdk:main\n\n"
        "[opentelemetry_traces_exporter]\nconsole = opentelemetry.sdk.trace.export:ConsoleSpanExporter\n\n"
        "[opentelemetry_environment_variables]\nsdk = opentelemetry.sdk.environment_variables\n",
    )
    metadata_dir = destination / "_metadata"

    count = write_metadata([package], destination, metadata_dir, NAMESPACE, NAMES)

    assert count == 2
    dist_info = metadata_dir / "opentelemetry_sdk-1.0.dist-info"
    assert sorted(path.name for path in dist_info.iterdir()) == ["METADATA", "entry_points.txt"]
    assert (dist_info / "entry_points.txt").read_text() == (
        "[opentelemetry_traces_exporter]\n"
        "console = opentelemetry.agent._vendor.opentelemetry.sdk.trace.export:ConsoleSpanExporter\n"
        "\n"
        "[opentelemetry_environment_variables]\n"
        "sdk = opentelemetry.agent._vendor.opentelemetry.sdk.environment_variables\n"
    )
    # importlib.metadata finds the copy only through an explicit path.
    [distribution] = distributions(path=[str(metadata_dir)])
    assert distribution.metadata["Name"] == "opentelemetry-sdk"
    assert distribution.requires == ['wrapt; extra == "instruments"']
    [entry_point] = distribution.entry_points.select(group="opentelemetry_traces_exporter")
    assert entry_point.module == "opentelemetry.agent._vendor.opentelemetry.sdk.trace.export"
    assert entry_point.dist is not None


def test_write_metadata_without_entry_points(tmp_path: Path) -> None:
    destination = _vendored_tree(tmp_path)

    assert write_metadata([_package(tmp_path, None)], destination, destination / "_metadata", NAMESPACE, NAMES) == 0

    dist_info = destination / "_metadata" / "opentelemetry_sdk-1.0.dist-info"
    assert [path.name for path in dist_info.iterdir()] == ["METADATA"]


def test_write_metadata_only_script_entry_points(tmp_path: Path) -> None:
    destination = _vendored_tree(tmp_path)
    package = _package(tmp_path, "[console_scripts]\nscript = opentelemetry.sdk:main\n")

    write_metadata([package], destination, destination / "_metadata", NAMESPACE, NAMES)

    assert not (destination / "_metadata" / "opentelemetry_sdk-1.0.dist-info" / "entry_points.txt").exists()


@pytest.mark.parametrize(
    ("value", "module"),
    [
        pytest.param(
            "opentelemetry.exporter.otlp.proto.grpc:OTLPSpanExporter",
            "opentelemetry.agent._vendor.opentelemetry.exporter.otlp.proto.grpc",
            id="missing-vendored-module",
        ),
        pytest.param("aiohttp.client:ClientSession", "aiohttp.client", id="non-vendored-module"),
    ],
)
def test_write_metadata_missing_module(tmp_path: Path, value: str, module: str) -> None:
    destination = _vendored_tree(tmp_path, "opentelemetry/sdk/__init__.py")
    package = _package(tmp_path, f"[opentelemetry_traces_exporter]\notlp = {value}\n")

    with pytest.raises(VendorError) as exc_info:
        write_metadata([package], destination, destination / "_metadata", NAMESPACE, NAMES)

    assert str(exc_info.value) == (
        f"entry point opentelemetry_traces_exporter:otlp of opentelemetry-sdk references {module}, "
        "which isn't in the vendored tree"
    )
