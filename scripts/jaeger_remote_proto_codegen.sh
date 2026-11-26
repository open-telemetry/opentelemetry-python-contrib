#!/bin/bash
# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# Regenerate python code from the vendored sampling.proto in
# sampler/opentelemetry-sampler-jaeger-remote/sampling.proto
#
# To update, manually diff the vendored sampling.proto against the latest upstream file, re-apply
# the same stripping to any upstream changes, update the pinned commit noted in the header comment
# of sampling.proto, then run this script to regenerate the python code. Commit the changes as
# well as any fixes needed in the sampler.

set -e

# root of opentelemetry-python-contrib repo
repo_root="$(git rev-parse --show-toplevel)"
package_root="$repo_root/sampler/opentelemetry-sampler-jaeger-remote"
proto_output_dir="$package_root/src/opentelemetry/sampler/jaeger/remote/proto"

protoc() {
    uvx -c $package_root/gen-requirements.txt \
        --python 3.12 \
        --from grpcio-tools \
        --with mypy-protobuf \
        python -m grpc_tools.protoc "$@"
}

protoc --version

# clean up old generated code
find $proto_output_dir -regex ".*_pb2.*\.pyi?" -exec rm {} +

# generate message code
protoc \
    -I $package_root \
    --python_out=$proto_output_dir \
    --mypy_out=$proto_output_dir \
    $package_root/sampling.proto

# sampling.proto also defines the SamplingManager service, so generate grpc stubs too
protoc \
    -I $package_root \
    --grpc_python_out=$proto_output_dir \
    $package_root/sampling.proto

sed 's/import sampling_pb2 as sampling__pb2/from . import sampling_pb2 as sampling__pb2/' $proto_output_dir/sampling_pb2_grpc.py > $proto_output_dir/sampling_pb2_grpc.py.tmp
mv $proto_output_dir/sampling_pb2_grpc.py.tmp $proto_output_dir/sampling_pb2_grpc.py
