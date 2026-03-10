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

import glob
import json
import os
from typing import Any, Dict, List

try:
    import tomli
except ImportError:
    import tomllib as tomli

from otel_packaging import root_path

GENAI_INSTRUMENTATION_PATH = os.path.join(root_path, "instrumentation-genai")


def get_genai_packages(
    metadata_keys: List[str] = None,
) -> List[Dict[str, Any]]:
    """Finds all GenAI instrumentation packages and parses their metadata."""
    packages = []
    if metadata_keys is None:
        metadata_keys = []

    for pyproject_path in glob.glob(
        os.path.join(GENAI_INSTRUMENTATION_PATH, "*/pyproject.toml")
    ):
        try:
            with open(pyproject_path, "rb") as f:
                pyproject_data = tomli.load(f)

            package_name = pyproject_data.get("project", {}).get("name")
            if not package_name:
                continue

            pkg_info = {
                "name": package_name,
                "path": os.path.dirname(pyproject_path),
            }

            metadata = (
                pyproject_data.get("tool", {})
                .get("opentelemetry", {})
                .get("instrumentation", {})
            )

            # Default values
            pkg_info["independent_release"] = metadata.get(
                "independent_release", False
            )
            pkg_info["include_in_bootstrap"] = metadata.get(
                "include_in_bootstrap", False
            )

            for key in metadata_keys:
                pkg_info[key] = metadata.get(key)

            packages.append(pkg_info)

        except Exception as e:
            print(f"Error processing {pyproject_path}: {e}")

    return sorted(packages, key=lambda p: p["name"])


def get_independent_release_packages() -> List[str]:
    """Returns a list of package names that have independent_release = true."""
    packages = get_genai_packages()
    return [pkg["name"] for pkg in packages if pkg.get("independent_release")]


if __name__ == "__main__":
    # Example usage: Output JSON list of independent packages for GitHub Actions
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--independent-json":
        print(json.dumps(get_independent_release_packages()))
    else:
        print("Discovered GenAI Packages:")
        for pkg in get_genai_packages():
            print(f"  - {pkg['name']}: {pkg}")
