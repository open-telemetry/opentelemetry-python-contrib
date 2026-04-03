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


# Get the latest versions of packaging tools
python3 -m pip install --upgrade pip build setuptools wheel packaging

# Validate version against PEP 440 conventions: https://packaging.pypa.io/en/latest/version.html
python3 -c "from packaging.version import Version; Version('${pkg_version}')"

basedir=$(git rev-parse --show-toplevel)
cd $basedir

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

python3 -m build --outdir ${distdir}

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
pip wheel --no-deps $pkg_tar_gz_file
