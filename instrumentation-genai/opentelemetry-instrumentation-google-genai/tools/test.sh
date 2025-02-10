#!/bin/bash

SCRIPT_DIR=$(cd $(dirname "${BASH_SOURCE:-$0}"); pwd)
PROJECT_DIR=$(readlink -f "${SCRIPT_DIR}/..")
TESTS_DIR="${PROJECT_DIR}/tests"
TESTS_OUTPUT_DIR="${PROJECT_DIR}/.test"
TEST_ENV="${TESTS_OUTPUT_DIR}/.test/.venv"

function main() {
    if [ ! -d "${TEST_ENV}" ] ; then
      mkdir -p "${TEST_ENV}" || exit 1
    fi
    if [ ! -e "${TEST_ENV}/bin/activate" ] ; then
      python3 -m venv "${TEST_ENV}" || exit 1
    fi
    source "${TEST_ENV}/bin/activate" || exit 1
    pip install -r "${TESTS_DIR}/requirements.txt" || exit 1
    pip install tox || exit 1
    cd "${PROJECT_DIR}" || exit 1
    make install || exit 1
    python3 -m tox || exit 1
}

main
