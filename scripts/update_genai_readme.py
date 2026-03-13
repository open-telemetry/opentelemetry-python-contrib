#!/usr/bin/env python3
# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from pathlib import Path

# TODO: Unify README generation with `scripts/generate_instrumentation_readme.py`
# Currently, this script (GenAI) parses package metadata statically from `[project.optional-dependencies]`
# and `[tool.opentelemetry.instrumentation]` within pyproject.toml via `tomli`.
#
# The legacy generation script (`generate_instrumentation_readme.py`) dynamically evaluates
# Python `package.py` files using `exec()` to extract version-bound dependency strings (e.g. `aiohttp ~= 3.0`)
# from internal python variables like `_instruments` and `_supports_metrics`.
import tomli
from discover_genai_packages import (
    GENAI_INSTRUMENTATION_PATH,
    get_genai_packages,
)

ROOT_PATH = Path(__file__).parent.parent
GENAI_PATH = Path(GENAI_INSTRUMENTATION_PATH)
README_PATH = GENAI_PATH / "README.md"

START_MARKER = "<!-- BEGIN GENERATED TABLE -->"
END_MARKER = "<!-- END GENERATED TABLE -->"

TABLE_HEADER = [
    "| Instrumentation | Supported Packages | Metrics support | Semconv status |",
    "| --------------- | ------------------ | --------------- | -------------- |",
]


def generate_table_rows():
    packages = get_genai_packages(
        metadata_keys=["readme_sia", "readme_status"]
    )
    rows = []

    for pkg in packages:
        name = pkg["name"]
        pkg_path = Path(pkg["path"])
        try:
            relative_path = pkg_path.relative_to(GENAI_PATH)
        except ValueError:
            relative_path = pkg_path  # Should not happen given discovery logic

        pyproject_path = pkg_path / "pyproject.toml"
        supported_packages = ""
        try:
            with open(pyproject_path, "rb") as f:
                pyproject_data = tomli.load(f)
            instruments = (
                pyproject_data.get("project", {})
                .get("optional-dependencies", {})
                .get("instruments", [])
            )
            if isinstance(instruments, list):
                supported_packages = ", ".join(instruments)
        except Exception:
            pass

        metrics_support_val = pkg.get("readme_metrics", False)
        metrics_support = "Yes" if metrics_support_val else "No"
        status = pkg.get("readme_status", "development").lower()

        row = f"| [{name}](./{relative_path}) | {supported_packages} | {metrics_support} | {status} |"
        rows.append(row)

    return rows


if __name__ == "__main__":
    table_rows = generate_table_rows()
    with open(README_PATH, "r", encoding="utf-8") as f:
        readme_content = f.read()

    start_index = readme_content.find(START_MARKER)
    end_index = readme_content.find(END_MARKER)

    if start_index == -1 or end_index == -1:
        print(f"Error: Markers not found in {README_PATH}")
        print(
            f"Please add '{START_MARKER}' and '{END_MARKER}' around the table in the README."
        )
        exit(1)

    # Content before the marker, including the marker itself
    content_before = readme_content[: start_index + len(START_MARKER)]

    # Content after the marker, including the marker itself
    content_after = readme_content[end_index:]

    table_rows = generate_table_rows()
    new_table = "\n".join(TABLE_HEADER + [""] + table_rows)

    new_content = f"{content_before}\n{new_table}\n{content_after}"

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"Updated {README_PATH}")
