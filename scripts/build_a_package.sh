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

if [ -z $GITHUB_REF ]; then
  echo 'Failed to run script, missing workflow env variable GITHUB_REF'
  exit -1
fi

PKG_NAME_AND_VERSION=${GITHUB_REF#refs/tags/*}
PKG_NAME=${PKG_NAME_AND_VERSION%==*}
PKG_VERSION=${PKG_NAME_AND_VERSION#opentelemetry-*==}

# Get the latest versions of packaging tools
python3 -m pip install --upgrade pip setuptools wheel packaging

# Validate vesrion against PEP 440 conventions: https://packaging.pypa.io/en/latest/version.html
python3 -c "from packaging.version import Version; Version('${PKG_VERSION}')"

BASEDIR=$(git rev-parse --show-toplevel)
cd $BASEDIR

DISTDIR=${BASEDIR}/dist
mkdir -p $DISTDIR
rm -rf $DISTDIR/*

SETUP_PY_FILE_PATTERN=$(ls -U **/$PKG_NAME/setup.py)
DIRECTORY_WITH_PACKAGE=$(dirname $SETUP_PY_FILE_PATTERN)

cd $DIRECTORY_WITH_PACKAGE

python3 setup.py sdist --dist-dir ${DISTDIR} clean --all

cd $DISTDIR

PKG_TAR_GZ_FILE=${PKG_NAME}-${PKG_VERSION}.tar.gz

if ! [ -f $PKG_TAR_GZ_FILE ]; then
  echo 'Error! Tag version does not match version built using latest package files.'
  exit -1
fi

# Build a wheel for the source distribution
pip wheel --no-deps $PKG_TAR_GZ_FILE
