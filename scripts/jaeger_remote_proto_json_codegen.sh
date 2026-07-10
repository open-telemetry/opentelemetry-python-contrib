#!/bin/bash
# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# Regenerate JSON (de)serialization python code from the vendored sampling.proto in
# sampler/opentelemetry-sampler-jaeger-remote/sampling.proto
# (see scripts/jaeger_remote_proto_codegen.sh for the protobuf/gRPC bindings generated from the
# same vendored proto).
#
# This uses the opentelemetry-codegen-json protoc plugin from the opentelemetry-python repo
# (https://github.com/open-telemetry/opentelemetry-python/tree/main/codegen/opentelemetry-codegen-json)
#
# To update, update CODEGEN_JSON_REPO_BRANCH_OR_COMMIT below to a commit hash or tag in the
# opentelemetry-python repo that you want to build off of, then run this script and commit the
# changes as well as any fixes needed in the sampler.

# Pinned commit for the opentelemetry-codegen-json plugin used to generate this code.
CODEGEN_JSON_REPO_BRANCH_OR_COMMIT="634cec5f2a2fecb40cb9d8216888c7b8865b845a"

set -e

#CODEGEN_JSON_PACKAGE="opentelemetry-codegen-json @ git+https://github.com/open-telemetry/opentelemetry-python.git@${CODEGEN_JSON_REPO_BRANCH_OR_COMMIT}#subdirectory=codegen/opentelemetry-codegen-json"
CODEGEN_JSON_PACKAGE="/Users/lukas/Documents/github-projects/opentelemetry-python/codegen/opentelemetry-codegen-json"

# root of opentelemetry-python-contrib repo
repo_root="$(git rev-parse --show-toplevel)"
package_root="$repo_root/sampler/opentelemetry-sampler-jaeger-remote"
sampler_root="$package_root/src/opentelemetry/sampler/jaeger/remote"
proto_json_dir="$sampler_root/proto_json"

protoc() {
    uvx -c $package_root/gen-requirements.txt \
        --python 3.12 \
        --from grpcio-tools \
        --with "$CODEGEN_JSON_PACKAGE" \
        python -m grpc_tools.protoc "$@"
}

protoc --version

mkdir -p $proto_json_dir

# clean up old generated code, but keep the hand-authored __init__.py
find $proto_json_dir -name "*.py" -not -name "__init__.py" -delete
rm -rf $proto_json_dir/version

protoc \
    -I $package_root \
    --otlp_json_out=$proto_json_dir \
    $package_root/sampling.proto

# fix json codec import
sed 's/^import _json_codec$/from . import _json_codec/' $proto_json_dir/sampling.py > $proto_json_dir/sampling.py.tmp
mv $proto_json_dir/sampling.py.tmp $proto_json_dir/sampling.py

# remove unneeded version files
rm -rf $proto_json_dir/version
