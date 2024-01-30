#!/bin/bash

set -e

function cov {
<<<<<<< HEAD
    pytest \
        --cov ${1} \
        --cov-append \
        --cov-branch \
        --cov-report='' \
        ${1}
=======
    if [ ${TOX_ENV_NAME:0:4} == "py34" ]
    then
        pytest \
            --ignore-glob=instrumentation/opentelemetry-instrumentation-opentracing-shim/tests/testbed/* \
            --cov ${1} \
            --cov-append \
            --cov-branch \
            --cov-report='' \
            ${1}
    else
        pytest \
            --cov ${1} \
            --cov-append \
            --cov-branch \
            --cov-report='' \
            ${1}
    fi
>>>>>>> upstream/main
}

PYTHON_VERSION=$(python -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')
PYTHON_VERSION_INFO=(${PYTHON_VERSION//./ })

coverage erase

<<<<<<< HEAD
cov instrumentation/opentelemetry-instrumentation-flask
cov instrumentation/opentelemetry-instrumentation-requests
cov instrumentation/opentelemetry-instrumentation-wsgi
cov instrumentation/opentelemetry-instrumentation-aiohttp-client
cov instrumentation/opentelemetry-instrumentation-asgi


=======
cov opentelemetry-api
cov opentelemetry-sdk
cov exporter/opentelemetry-exporter-datadog
cov instrumentation/opentelemetry-instrumentation-flask
cov instrumentation/opentelemetry-instrumentation-requests
cov instrumentation/opentelemetry-instrumentation-opentracing-shim
cov util/opentelemetry-util-http
cov exporter/opentelemetry-exporter-zipkin


cov instrumentation/opentelemetry-instrumentation-aiohttp-client
cov instrumentation/opentelemetry-instrumentation-asgi

>>>>>>> upstream/main
coverage report --show-missing
coverage xml
