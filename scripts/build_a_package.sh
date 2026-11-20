#!/bin/sh

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

# This script builds wheels for a single package when triggered from per-package release
# GitHub workflow (see .github/package-release.yml).
# The wheel is then published to PyPI by the workflow.

set -ev

if [ $PACKAGE_NAME ]; then
  pkg_name=${PACKAGE_NAME}
  pkg_version=${VERSION}
elif [ $GITHUB_REF ]; then
  pkg_name_and_version=${GITHUB_REF#refs/tags/*}
  pkg_name=${pkg_name_and_version%==*}
  pkg_version=${pkg_name_and_version#opentelemetry-*==}
else
  echo 'Failed to run script, missing workflow env variable GITHUB_REF or PACKAGE_NAME and VERSION.'
  exit 1
fi


basedir=$(git rev-parse --show-toplevel)

# Get the versions of packaging tools recorded in the lockfile
uv sync --locked --only-group build --project "$basedir"
PATH="$basedir/.venv/bin:$PATH"
export PATH

# Exclude packages uploaded within the last 3 days across subsequent uv invocations,
# ensuring build backend dependencies (e.g. hatchling) also inherit the cutoff.
export UV_EXCLUDE_NEWER=3d

# Validate version against PEP 440 conventions: https://packaging.pypa.io/en/latest/version.html
python3 -c "from packaging.version import Version; Version('${pkg_version}')"

cd $basedir

# Ensure no untracked or modified files exist in the checkout before building
if [ -n "$(git status --porcelain)" ]; then
  echo "Error! Working tree is dirty before build:"
  git status --porcelain
  exit 1
fi

distdir=${basedir}/dist
mkdir -p $distdir
rm -rf ${distdir:?}/*

pyproject_toml_file_path=$(ls **/$pkg_name/pyproject.toml)

if [ -z $pyproject_toml_file_path ]; then
  echo "Error! pyproject.toml not found for $pkg_name, can't build."
  exit 1
fi

directory_with_package=$(dirname $pyproject_toml_file_path)

cd $directory_with_package

uv build --sdist --out-dir ${distdir}
rm -f "${distdir}/.gitignore"

cd $distdir

pkg_tar_gz_file=`echo $pkg_name | sed 's/-/_/g'`-${pkg_version}.tar.gz

echo "Checking if $pkg_tar_gz_file exists in dist/ directory."

# print the list of files in current directory
echo "$(ls)"

if ! [ -f $pkg_tar_gz_file ]; then
  echo 'Error! Tag version does not match version built using latest package files.'
  exit 1
fi

# Build a wheel for the source distribution
uv build --wheel --out-dir ${distdir} $pkg_tar_gz_file
rm -f "${distdir}/.gitignore"

# Audit built wheel contents against startup-hook (.pth / sitecustomize.py)
# and *.data/ injection attacks (e.g., LiteLLM v1.107.0 supply-chain vector).
python3 - "$distdir" "$pkg_name" "$pkg_version" <<'PYEOF'
import pathlib
import sys
import zipfile

distdir = pathlib.Path(sys.argv[1])
pkg_name_norm = sys.argv[2].replace("-", "_")
pkg_version = sys.argv[3]
expected_dist_info = f"{pkg_name_norm}-{pkg_version}.dist-info/"

wheels = list(distdir.glob(f"{pkg_name_norm}-{pkg_version}-*.whl"))
if len(wheels) != 1:
    sys.exit(f"Error! Expected exactly 1 wheel in {distdir}, found: {wheels}")

with zipfile.ZipFile(wheels[0]) as zf:
    for name in zf.namelist():
        basename = pathlib.PurePosixPath(name).name
        if name.endswith(".pth") or (
            basename in {"sitecustomize.py", "usercustomize.py"}
            and name != "opentelemetry/instrumentation/auto_instrumentation/sitecustomize.py"
        ):
            sys.exit(f"Error! Forbidden startup hook file in wheel: {name}")
        if not (name.startswith("opentelemetry/") or name.startswith(expected_dist_info)):
            sys.exit(
                f"Error! Unexpected top-level path in wheel: {name} "
                f"(expected 'opentelemetry/' or '{expected_dist_info}')"
            )

print(f"Verified wheel contents for {wheels[0].name} ({len(zf.namelist())} files).")
PYEOF
