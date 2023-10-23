#!/usr/bin/env bash
set -euxo pipefail

DOCKER_DIR="$(pwd)"
pushd ../instrumentation/opentelemetry-instrumentation-pubsub
  python -m build --outdir "$DOCKER_DIR"
popd
WHEEL="$(find . -name '*.whl')"

TAG=eu.gcr.io/annotell-com/opentelemetry-python-instrumentation/python:0.42b0-SNAPSHOT-9
docker build . \
  -t $TAG \
  --platform linux/amd64 --push
#  --build-arg="WHEEL=$WHEEL" \
#  --progress=plain &> build.log

#docker run -it $TAG ls /autoinstrumentation/opentelemetry/instrumentation
