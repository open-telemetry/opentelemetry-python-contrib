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
TOP_LEVEL_DIR=$(readlink -f "${PROJECT_DIR}/../../")
TESTS_DIR="${PROJECT_DIR}/tests"
TESTS_OUTPUT_DIR="${PROJECT_DIR}/.test"
TEST_ENV="${TESTS_OUTPUT_DIR}/.venv"

function run_tox_test() {
    local tox_env="$1"
    tox -e "${tox_env}" -- -o log_cli_level=debug 
}

function main() {
    if [ ! -d "${TEST_ENV}" ] ; then
      mkdir -p "${TEST_ENV}" || exit 1
    fi
    if [ ! -e "${TEST_ENV}/bin/activate" ] ; then
      python3 -m venv "${TEST_ENV}" || exit 1
    fi
    source "${TEST_ENV}/bin/activate" || exit 1
    pip install tox || exit 1
    pip install pytest || exit 1
    cd "${TOP_LEVEL_DIR_DIR}" || exit 1

    local tox_environments=$(tox -l | grep 'test-instrumentation-google-genai')
    local successful=0
    for tox_environment in ${tox_environments} ; do
      echo "[INFO] Testing environment: ${tox_environmenmt}" >&2
      ${SCRIPT_DIR}/test-with-tox.sh "${tox_environment}"|| exit $?
      successful=$(expr ${successful} + 1)
    done
    if [ $successful -eq 0 ] ; then
      echo "[FATAL] No tests ran." >&2
      exit 1
    fi
    echo "[DONE] Succesfully passed ${successful} environments." >&2
}

main
