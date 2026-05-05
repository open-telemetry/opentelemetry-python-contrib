#!/usr/bin/env python3
import argparse, os, re, sys
from pathlib import Path

SPDX_HEADER = "# Copyright The OpenTelemetry Authors\n# SPDX-License-Identifier: Apache-2.0"

APACHE_PATTERN = re.compile(r"# Copyright The OpenTelemetry Authors\r?\n#\r?\n# Licensed under the Apache License, Version 2\.0 \(the \"License\"\);\r?\n# you may not use this file except in compliance with the License\.\r?\n# You may obtain a copy of the License at\r?\n#\r?\n#\s+http://www\.apache\.org/licenses/LICENSE-2\.0\r?\n#\r?\n# Unless required by applicable law or agreed to in writing, software\r?\n# distributed under the License is distributed on an \"AS IS\" BASIS,\r?\n# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied\.\r?\n# See the License for the specific language governing permissions and\r?\n# limitations under the License\.")

APACHE_PATTERN_OLD = re.compile(r"# Copyright \d{4},? OpenTelemetry Authors\r?\n#\r?\n# Licensed under the Apache License, Version 2\.0 \(the \"License\"\);\r?\n# you may not use this file except in compliance with the License\.\r?\n# You may obtain a copy of the License at\r?\n#\r?\n#\s+http://www\.apache\.org/licenses/LICENSE-2\.0\r?\n#\r?\n# Unless required by applicable law or agreed to in writing, software\r?\n# distributed under the License is distributed on an \"AS IS\" BASIS,\r?\n# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied\.\r?\n# See the License for the specific language governing permissions and\r?\n# limitations under the License\.")

SPDX_PATTERN = re.compile(r"# Copyright The OpenTelemetry Authors\r?\n# SPDX-License-Identifier: Apache-2\.0")
ANY_COPYRIGHT_PATTERN = re.compile(r"# Copyright|# Licensed under|SPDX-License-Identifier", re.IGNORECASE)

def process_file(path, dry_run):
    try:
        raw = path.read_bytes()
    except OSError as e:
        print(f"  ERROR reading {path}: {e}"); return "error"
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        content = raw.decode("latin-1")
    if SPDX_PATTERN.search(content): return "already"
    for pat in [APACHE_PATTERN, APACHE_PATTERN_OLD]:
        if pat.search(content):
            new_content = pat.sub(SPDX_HEADER, content, count=1)
            if not dry_run:
                try: path.write_text(new_content, encoding="utf-8")
                except OSError as e: print(f"  ERROR writing {path}: {e}"); return "error"
            return "replaced"
    if ANY_COPYRIGHT_PATTERN.search(content): return "variant"
    return "no_header"

def find_py_files(root):
    SKIP = {".git",".tox",".venv","venv","__pycache__",".eggs","build","dist","node_modules"}
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP]
        for f in fns:
            if f.endswith(".py"): yield Path(dp)/f

def main():
    p = argparse.ArgumentParser()
    p.add_argument("repo_root"); p.add_argument("--dry-run", action="store_true"); p.add_argument("--report-variants", action="store_true")
    args = p.parse_args()
    root = Path(args.repo_root).resolve()
    if not root.is_dir(): print(f"ERROR: {root} is not a directory."); sys.exit(1)
    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Scanning: {root}\n")
    counts = {"replaced":0,"already":0,"no_header":0,"variant":0,"error":0}
    variants = []
    for f in sorted(find_py_files(root)):
        r = process_file(f, args.dry_run); counts[r] += 1
        if r == "replaced": print(f"  {'[would replace]' if args.dry_run else '[replaced]    '} {f.relative_to(root)}")
        elif r == "variant": variants.append(str(f.relative_to(root)))
        elif r == "error": print(f"  [error] {f.relative_to(root)}")
    print("\n" + "-"*60)
    print(f"{'DRY RUN SUMMARY' if args.dry_run else 'SUMMARY'}")
    print("-"*60)
    print(f"  Total .py files scanned : {sum(counts.values())}")
    print(f"  {'Would replace' if args.dry_run else 'Replaced'}       : {counts['replaced']}")
    print(f"  Already SPDX            : {counts['already']}")
    print(f"  No OTel header          : {counts['no_header']}")
    print(f"  Variant headers         : {counts['variant']}")
    print(f"  Errors                  : {counts['error']}")
    print("-"*60)
    if args.report_variants and variants:
        print(f"\nVariant headers ({len(variants)}) — review manually:")
        for v in variants: print(f"  {v}")
    if args.dry_run and counts["replaced"] > 0: print(f"\nDry run complete. Re-run WITHOUT --dry-run to apply {counts['replaced']} changes.")
    elif not args.dry_run and counts["replaced"] > 0: print(f"\nDone! {counts['replaced']} files updated.")
    else: print("\nNothing to do.")

if __name__ == "__main__": main()
