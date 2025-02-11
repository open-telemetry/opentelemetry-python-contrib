#!/bin/bash

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

SCRIPT_DIR=$(cd $(dirname "${BASH_SOURCE:-$0}"); pwd)
PROJECT_DIR=$(readlink -f "${SCRIPT_DIR}/..")
BUILD_DIR="${PROJECT_DIR}/.build"
BUILD_ENV="${BUILD_DIR}/.venv"

function main() {
    if [ ! -d "${BUILD_ENV}" ] ; then
      mkdir -p "${BUILD_ENV}" || exit 1
    fi
    if [ ! -e "${BUILD_ENV}/bin/activate" ] ; then
      python3 -m venv "${BUILD_ENV}" || exit 1
    fi
    source "${BUILD_ENV}/bin/activate" || exit 1
    pip install hatch || exit 1
    hatch build || exit 1
}

main
