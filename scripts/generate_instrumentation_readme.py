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

import logging
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("instrumentation_readme_generator")

_prefix = "opentelemetry-instrumentation-"

header = """
| Instrumentation | Supported Packages | Metrics support | Semconv status |
| --------------- | ------------------ | --------------- | -------------- |"""


def main(base_instrumentation_path):
    table = [header]
    for instrumentation in sorted(os.listdir(base_instrumentation_path)):
        instrumentation_path = os.path.join(
            base_instrumentation_path, instrumentation
        )
        if not os.path.isdir(
            instrumentation_path
        ) or not instrumentation.startswith(_prefix):
            continue

        src_dir = os.path.join(
            instrumentation_path, "src", "opentelemetry", "instrumentation"
        )
        src_pkgs = [
            f
            for f in os.listdir(src_dir)
            if os.path.isdir(os.path.join(src_dir, f))
        ]
        assert len(src_pkgs) == 1
        name = src_pkgs[0]

        pkg_info = {}
        version_filename = os.path.join(
            src_dir,
            name,
            "package.py",
        )
        with open(version_filename, encoding="utf-8") as fh:
            exec(fh.read(), pkg_info)

        instruments_and = pkg_info.get("_instruments", ())
        # _instruments_any is an optional field that can be used instead of or in addition to _instruments. While _instruments is a list of dependencies, all of which are expected by the instrumentation, _instruments_any is a list any of which but not all are expected.
        instruments_any = pkg_info.get("_instruments_any", ())
        supports_metrics = pkg_info.get("_supports_metrics")
        semconv_status = pkg_info.get("_semconv_status")
        instruments_all = ()
        if not instruments_and and not instruments_any:
            instruments_all = (name,)
        else:
            instruments_all = tuple(instruments_and + instruments_any)

        if not semconv_status:
            semconv_status = "development"

        metric_column = "Yes" if supports_metrics else "No"

        table.append(
            f"| [{instrumentation}](./{instrumentation}) | {','.join(instruments_all)} | {metric_column} | {semconv_status}"
        )

    with open(
        os.path.join(base_instrumentation_path, "README.md"),
        "w",
        encoding="utf-8",
    ) as fh:
        fh.write("\n".join(table))


if __name__ == "__main__":
    root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    instrumentation_path = os.path.join(root_path, "instrumentation")
    main(instrumentation_path)
    genai_instrumentation_path = os.path.join(
        root_path, "instrumentation-genai"
    )
    main(genai_instrumentation_path)
