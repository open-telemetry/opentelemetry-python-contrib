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

from tomli import load
from os import path, listdir
from subprocess import check_output, CalledProcessError
from requests import get

scripts_path = path.dirname(path.abspath(__file__))
root_path = path.dirname(scripts_path)
instrumentations_path = path.join(root_path, "instrumentation")


def get_instrumentation_packages():
    for pkg in sorted(listdir(instrumentations_path)):
        pkg_path = path.join(instrumentations_path, pkg)
        if not path.isdir(pkg_path):
            continue

        error = f"Could not get version for package {pkg}"

        try:
            hatch_version = check_output(
                "hatch version",
                shell=True,
                cwd=pkg_path,
                universal_newlines=True
            )

        except CalledProcessError as exc:
            print(f"Could not get hatch version from path {pkg_path}")
            print(exc.output)

        try:
            response = get(f"https://pypi.org/pypi/{pkg}/json", timeout=10)

        except Exception:
            print(error)
            continue

        if response.status_code != 200:
            print(error)
            continue

        pyproject_toml_path = path.join(pkg_path, "pyproject.toml")

        with open(pyproject_toml_path, "rb") as file:
            pyproject_toml = load(file)

        instrumentation = {
            "name": pyproject_toml["project"]["name"],
            "version": hatch_version.strip(),
            "instruments": pyproject_toml["project"]["optional-dependencies"][
                "instruments"
            ],
        }
        instrumentation["requirement"] = "==".join(
            (
                instrumentation["name"],
                instrumentation["version"],
            )
        )
        yield instrumentation


if __name__ == "__main__":
    print(list(get_instrumentation_packages()))
