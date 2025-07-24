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

from __future__ import annotations

import os
import subprocess
from subprocess import CalledProcessError

import tomli

scripts_path = os.path.dirname(os.path.abspath(__file__))
root_path = os.path.dirname(scripts_path)
instrumentations_path = os.path.join(root_path, "instrumentation")
genai_instrumentations_path = os.path.join(root_path, "instrumentation-genai")


def get_instrumentation_packages(
    independent_packages: dict[str, str] | None = None,
):
    independent_packages = independent_packages or {}
    pkg_paths = []
    for pkg in os.listdir(instrumentations_path):
        pkg_path = os.path.join(instrumentations_path, pkg)
        if not os.path.isdir(pkg_path):
            continue
        pkg_paths.append(pkg_path)
    for pkg in os.listdir(genai_instrumentations_path):
        pkg_path = os.path.join(genai_instrumentations_path, pkg)
        if not os.path.isdir(pkg_path):
            continue
        pkg_paths.append(pkg_path)

    for pkg_path in sorted(pkg_paths):
        try:
            version = subprocess.check_output(
                "hatch version",
                shell=True,
                cwd=pkg_path,
                universal_newlines=True,
            )
        except CalledProcessError as exc:
            print(f"Could not get hatch version from path {pkg_path}")
            print(exc.output)
            raise exc

        pyproject_toml_path = os.path.join(pkg_path, "pyproject.toml")

        with open(pyproject_toml_path, "rb") as file:
            pyproject_toml = tomli.load(file)

        optional_dependencies = pyproject_toml["project"][
            "optional-dependencies"
        ]
        instruments = optional_dependencies.get("instruments", [])
        # instruments-any is an optional field that can be used instead of or in addition to instruments. While instruments is a list of dependencies, all of which are expected by the instrumentation, instruments-any is a list any of which but not all are expected.
        instruments_any = optional_dependencies.get("instruments-any", [])
        instrumentation = {
            "name": pyproject_toml["project"]["name"],
            "version": version.strip(),
            "instruments": instruments,
            "instruments-any": instruments_any,
        }
        if instrumentation["name"] in independent_packages:
            specifier = independent_packages[instrumentation["name"]]
            instrumentation["requirement"] = (
                f"{instrumentation['name']}{specifier}"
            )
        else:
            instrumentation["requirement"] = "==".join(
                (
                    instrumentation["name"],
                    instrumentation["version"],
                )
            )
        yield instrumentation


if __name__ == "__main__":
    print(list(get_instrumentation_packages()))
