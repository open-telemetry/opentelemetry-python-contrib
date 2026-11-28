# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from opentelemetry.vendor.metadata import VendoredPackage
from opentelemetry.vendor.patches import VendorPatch
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


def test_write_sbom_records_patches(tmp_path: Path) -> None:
    unpatched, patched = tmp_path / "unpatched.json", tmp_path / "patched.json"
    text = "Disable aliases.\n\ndiff --git a/urllib3/a.py b/urllib3/a.py\n"
    patch = VendorPatch(path=Path("urllib3.patch"), text=text, files=("urllib3/a.py",))

    write_sbom(PACKAGES, unpatched)
    write_sbom(PACKAGES, patched, {"urllib3": [patch]})

    unpatched_bom, patched_bom = json.loads(unpatched.read_text()), json.loads(patched.read_text())
    components = {c["name"]: c for c in patched_bom["components"]}
    assert components["urllib3"]["pedigree"] == {
        "patches": [{"type": "unofficial", "diff": {"text": {"content": text, "contentType": "text/plain"}}}]
    }
    assert "pedigree" not in components["idna"]
    assert all("pedigree" not in c for c in unpatched_bom["components"])
    assert patched_bom["serialNumber"] != unpatched_bom["serialNumber"]
