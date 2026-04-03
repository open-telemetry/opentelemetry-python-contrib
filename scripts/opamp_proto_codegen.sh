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

# Regenerate python code from opamp protos in
# https://github.com/open-telemetry/opamp-spec
#
# To use, update OPAMP_SPEC_REPO_BRANCH_OR_COMMIT variable below to a commit hash or
# tag in opentelemtry-proto repo that you want to build off of. Then, just run
# this script to update the proto files. Commit the changes as well as any
# fixes needed in the OTLP exporter.
#
# Optional envars:
#   OPAMP_SPEC_REPO_DIR - the path to an existing checkout of the opamp-spec repo

# Pinned commit/branch/tag for the current version used in the opamp python package.
OPAMP_SPEC_REPO_BRANCH_OR_COMMIT="v0.12.0"

set -e

OPAMP_SPEC_REPO_DIR=${OPAMP_SPEC_REPO_DIR:-"/tmp/opamp-spec"}
# root of opentelemetry-python repo
repo_root="$(git rev-parse --show-toplevel)"
proto_output_dir="$repo_root/opamp/opentelemetry-opamp-client/src/opentelemetry/_opamp/proto"

protoc() {
    uvx -c $repo_root/opamp-gen-requirements.txt \
        --python 3.12 \
        --from grpcio-tools \
        --with mypy-protobuf \
        python -m grpc_tools.protoc "$@"
}

protoc --version

# Clone the proto repo if it doesn't exist
if [ ! -d "$OPAMP_SPEC_REPO_DIR" ]; then
    git clone https://github.com/open-telemetry/opamp-spec.git $OPAMP_SPEC_REPO_DIR
fi

# Pull in changes and switch to requested branch
(
    cd $OPAMP_SPEC_REPO_DIR
    git fetch --all
    git checkout $OPAMP_SPEC_REPO_BRANCH_OR_COMMIT
    # pull if OPAMP_SPEC_BRANCH_OR_COMMIT is not a detached head
    git symbolic-ref -q HEAD && git pull --ff-only || true
)

cd $proto_output_dir

# clean up old generated code
find . -regex ".*_pb2.*\.pyi?" -exec rm {} +

# generate proto code for all protos
all_protos=$(find $OPAMP_SPEC_REPO_DIR/ -name "*.proto")
protoc \
    -I $OPAMP_SPEC_REPO_DIR/proto \
    --python_out=. \
    --mypy_out=. \
    $all_protos

sed -i -e 's/import anyvalue_pb2 as anyvalue__pb2/from . import anyvalue_pb2 as anyvalue__pb2/' opamp_pb2.py
