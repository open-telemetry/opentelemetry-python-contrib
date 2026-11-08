# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from opentelemetry.vendor.metadata import VendoredPackage
from opentelemetry.vendor.sbom import write_sbom


def _package(name: str, version: str, license_expression: str | None) -> VendoredPackage:
    return VendoredPackage(
        name=name,
        version=version,
        sha256=hashlib.sha256(name.encode()).hexdigest(),
        license_expression=license_expression,
        top_level_names=(name,),
        license_files={},
        dist_info=Path(f"{name}-{version}.dist-info"),
    )


PACKAGES = [
    _package("urllib3", "2.8.0", "MIT"),
    _package("certifi", "2026.10.23", "MPL-2.0"),
    _package("idna", "3.20", "BSD-3-Clause OR MIT"),
    _package("legacy", "1.0", "MIT License"),
    _package("unknown", "0.1", None),
]


def test_write_sbom(tmp_path: Path) -> None:
    path = tmp_path / "nested/bom.cdx.json"

    write_sbom(PACKAGES, path)

    bom = json.loads(path.read_text())
    assert bom["bomFormat"] == "CycloneDX"
    assert bom["specVersion"] == "1.6"
    assert "timestamp" not in bom["metadata"]
    components = {c["name"]: c for c in bom["components"]}
    assert list(components) == ["certifi", "idna", "legacy", "unknown", "urllib3"]
    assert components["urllib3"]["purl"] == "pkg:pypi/urllib3@2.8.0"
    assert components["urllib3"]["version"] == "2.8.0"
    assert components["urllib3"]["type"] == "library"
    assert components["urllib3"]["hashes"] == [{"alg": "SHA-256", "content": hashlib.sha256(b"urllib3").hexdigest()}]
    assert components["urllib3"]["licenses"] == [{"license": {"id": "MIT"}}]
    assert components["idna"]["licenses"] == [{"expression": "BSD-3-Clause OR MIT"}]
    assert components["legacy"]["licenses"] == [{"license": {"name": "MIT License"}}]
    assert "licenses" not in components["unknown"]


def test_write_sbom_is_deterministic(tmp_path: Path) -> None:
    first, second = tmp_path / "first.json", tmp_path / "second.json"

    write_sbom(PACKAGES, first)
    write_sbom(list(reversed(PACKAGES)), second)

    assert first.read_bytes() == second.read_bytes()
