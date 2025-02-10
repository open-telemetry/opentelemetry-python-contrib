#!/bin/bash

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
