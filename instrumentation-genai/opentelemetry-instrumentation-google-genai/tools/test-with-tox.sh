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

# Helper script of "test.sh".
#
# Assumptions:
#   - Working directory: top-level root project directory
#   - Virtual environment:
#       - Activated
#       - Contains the "tox" script
#   - Arguments:
#       - One argument
#       - Argument supplies name of a configured tox environment
#
# Action:
#
#   Runs the given tox environment, with additional parameters
#   to provide for more verbose debug output when testing.

function main() {
    local tox_env="$1"
    tox -e "${tox_env}" -- -o log_cli_level=debug
    exit $?
}

main "$@"
