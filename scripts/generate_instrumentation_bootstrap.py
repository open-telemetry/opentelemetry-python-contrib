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
import logging
import os
import subprocess
import sys

import astor
from otel_packaging import (
    get_instrumentation_packages,
    root_path,
    scripts_path,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("instrumentation_list_generator")

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

gen_path = os.path.join(
    root_path,
    "opentelemetry-instrumentation",
    "src",
    "opentelemetry",
    "instrumentation",
    "bootstrap_gen.py",
)

# AWS Lambda instrumentation is excluded from the default list because it often
# requires specific configurations and dependencies that may not be set up
# in all environments. Instead, users who need AWS Lambda support can opt-in
# by manually adding it to their environment.
# See https://github.com/open-telemetry/opentelemetry-python-contrib/issues/2787
packages_to_exclude = [
    "opentelemetry-instrumentation-aws-lambda",
    "opentelemetry-instrumentation-test",
]


def main():
    # pylint: disable=no-member
    default_instrumentations = ast.List(elts=[])
    libraries = ast.List(elts=[])
    for pkg in get_instrumentation_packages():
        if pkg.get("name") in packages_to_exclude:
            continue
        if not pkg["instruments"]:
            default_instrumentations.elts.append(ast.Str(pkg["requirement"]))
        for target_pkg in pkg["instruments"]:
            libraries.elts.append(
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
        os.path.join(scripts_path, "license_header.txt"), encoding="utf-8"
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
            "opentelemetry-instrumentation/src",
        ],
        check=True,
    )

    logger.info("generated %s", gen_path)


if __name__ == "__main__":
    main()
