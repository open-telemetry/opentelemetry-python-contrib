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

# This script builds wheels for a single package when trigged from a push to
# a tag as part of a GitHub workflow (See .github/publish-a-package.yml). The
# wheel is then published to PyPI.

set -ev

if [[ -z $GITHUB_REF ]]; then
  echo 'Failed to run script, missing workflow env variable GITHUB_REF'
  exit -1
fi

# Follows PEP 440 versioning conventions: https://www.python.org/dev/peps/pep-0440/#pre-releases
# Only allow publishing packages that are 1.0+ using this method
if ! [[ $GITHUB_REF =~ ^refs/tags/(opentelemetry-.*)==([1-9]([0-9]+)?\.[0-9]+((a|b|rc)[0-9]+)?(\.(post)?[0-9]+)?)$ ]]; then
  echo 'Failed to parse package name and package version from tag.'
  exit -1
fi

# From the capture groups in the regex above
PKG_NAME=${BASH_REMATCH[1]}
PKG_VERSION=${BASH_REMATCH[2]}

# Get the latest versions of packaging tools
python3 -m pip install --upgrade pip setuptools wheel

# If testing locally, change `BASEDIR` to your own repo directory
BASEDIR=$(dirname $(readlink -f $(dirname $0)))
cd $BASEDIR

DISTDIR=${BASEDIR}/dist
mkdir -p $DISTDIR
rm -rf $DISTDIR/*

for DIRECTORY_WITH_PACKAGE in exporter/*/ instrumentation/*/ propagator/*/ sdk-extension/*/ util/*/; do
  echo "Searching for $PKG_NAME in $DIRECTORY_WITH_PACKAGE"

  if [[ $DIRECTORY_WITH_PACKAGE =~ ^.*/$PKG_NAME/$ ]]; then
    echo "Found $PKG_NAME in $DIRECTORY_WITH_PACKAGE"

    cd $DIRECTORY_WITH_PACKAGE

    if ! [[ -f setup.py ]]; then
      echo "Error! setup.py not found in $DIRECTORY_WITH_PACKAGE, can't build."
      exit -1
    fi

    python3 setup.py sdist --dist-dir ${DISTDIR} clean --all

    break
  fi
done

cd $DISTDIR

PKG_TAR_GZ_FILE=${PKG_NAME}-${PKG_VERSION}.tar.gz

if ! [ -f $PKG_TAR_GZ_FILE ]; then
  echo 'Error! Tag version does not match version built using latest package files.'
  exit -1
fi

# Build a wheel for the source distribution
pip wheel --no-deps $PKG_TAR_GZ_FILE
