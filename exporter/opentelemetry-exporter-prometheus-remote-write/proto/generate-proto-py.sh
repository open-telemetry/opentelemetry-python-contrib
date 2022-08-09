#!/bin/bash

# Used libprotoc 3.21.1
SRC_DIR=opentelemetry/exporter/prometheus_remote_write/gen/
DST_DIR=../src/opentelemetry/exporter/prometheus_remote_write/gen/
protoc -I .  --python_out=../src ${SRC_DIR}/gogoproto/gogo.proto ${SRC_DIR}/remote.proto ${SRC_DIR}/types.proto
