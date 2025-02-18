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
TESTS_DIR="${PROJECT_DIR}/tests"
REQUIREMENTS_FILE="${TESTS_DIR}/requirements.txt"
TYPECHECK_ENV="${PROJECT_DIR}/.test/.typecheck-venv"

function main() {
    if [ ! -d "${TYPECHECK_ENV}" ] ; then
      mkdir -p "${TYPECHECK_ENV}" || exit 1
    fi
    if [ ! -e "${TYPECHECK_ENV}/bin/activate" ] ; then
      python3 -m venv "${TYPECHECK_ENV}" || exit 1
    fi
    source "${TYPECHECK_ENV}/bin/activate" || exit 1
    pip install pyright || exit 1
    pip install -r "${REQUIREMENTS_FILE}" || exit 1
    cd "${PROJECT_DIR}" || exit 1
    pyright --venvpath "${TYPECHECK_ENV}" || exit $?
}

main
