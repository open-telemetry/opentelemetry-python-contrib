# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path

import pytest

VALID_CONFIG = """
[tool.opentelemetry-vendor]
destination = "src/pkg/_vendor/"
requirements = "src/pkg/_vendor/requirements.txt"
namespace = "pkg._vendor"
python-version = "3.10"
protected-files = ["__init__.py", "requirements.txt"]
sbom-file = "src/pkg/_vendor/bom.cdx.json"
"""


@pytest.fixture(name="project_dir")
def fixture_project_dir(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text(VALID_CONFIG)
    destination = tmp_path / "src/pkg/_vendor"
    destination.mkdir(parents=True)
    (destination / "requirements.txt").write_text(
        "# comment\nsix==1.0 \\\n    --hash=sha256:0123456789abcdef\n    # via -r vendor.in\n"
    )
    return tmp_path
