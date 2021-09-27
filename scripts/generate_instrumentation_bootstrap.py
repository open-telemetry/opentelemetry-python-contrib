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

import ast
import filecmp
import logging
import os
import subprocess
import sys
import tempfile

import astor
import pkg_resources
import requests
from otel_packaging import (
    get_instrumentation_packages,
    scripts_path,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("instrumentation_list_generator")

_auto_generation_msg = """
# DO NOT EDIT. THIS FILE WAS AUTOGENERATED FROM templates/{source}.
# RUN `python scripts/generate_setup.py` TO REGENERATE.
"""

_template = """
{header}

# DO NOT EDIT. THIS FILE WAS AUTOGENERATED FROM INSTRUMENTATION PACKAGES.
# RUN `python scripts/generate_instrumentation_bootstrap.py` TO REGENERATE.

{source}
"""

_source_tmpl = """
libraries = {}
default_instrumentations = []
"""

tmpdir = tempfile.TemporaryDirectory()
gen_path = os.path.join(tmpdir.name, "new.py",)

current_path = os.path.join(tmpdir.name, "current.py",)

core_repo = os.getenv("CORE_REPO_SHA", "main")
url = "https://raw.githubusercontent.com/open-telemetry/opentelemetry-python/{}/opentelemetry-instrumentation/src/opentelemetry/instrumentation/bootstrap_gen.py".format(
    core_repo
)
r = requests.get(url, allow_redirects=True)
open(current_path, "wb").write(r.content)


def main():
    # pylint: disable=no-member
    default_instrumentations = ast.List(elts=[])
    libraries = ast.Dict(keys=[], values=[])
    for pkg in get_instrumentation_packages():
        if not pkg["instruments"]:
            default_instrumentations.elts.append(ast.Str(pkg["requirement"]))
        for target_pkg in pkg["instruments"]:
            parsed = pkg_resources.Requirement.parse(target_pkg)
            libraries.keys.append(ast.Str(parsed.name))
            libraries.values.append(
                ast.Dict(
                    keys=[ast.Str("library"), ast.Str("instrumentation")],
                    values=[ast.Str(target_pkg), ast.Str(pkg["requirement"])],
                )
            )

    tree = ast.parse(_source_tmpl)
    tree.body[0].value = libraries
    tree.body[1].value = default_instrumentations
    source = astor.to_source(tree)

    with open(
        os.path.join(scripts_path, "license_header.txt"), "r", encoding="utf-8"
    ) as header_file:
        header = header_file.read()
        source = _template.format(header=header, source=source)

    with open(gen_path, "w", encoding="utf-8") as gen_file:
        gen_file.write(source)

    subprocess.run(
        [
            sys.executable,
            "scripts/eachdist.py",
            "format",
            "--path",
            tmpdir.name,
        ],
        check=True,
    )

    logger.info("generated %s", gen_path)


def compare():
    if not filecmp.cmp(current_path, gen_path):
        logger.info(
            'Generated code is out of date, please run "tox -e generate" and commit bootstrap_gen.py to core repo.'
        )
        os.replace(gen_path, "bootstrap_gen.py")
        sys.exit(1)


if __name__ == "__main__":
    main()
    compare()
