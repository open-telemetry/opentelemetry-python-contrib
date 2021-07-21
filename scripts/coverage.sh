#!/bin/bash

set -e

function cov {
    pytest \
        --ignore-glob=*/setup.py \
        --cov ${1} \
        --cov-append \
        --cov-branch \
        --cov-report='' \
        ${1}
}

PYTHON_VERSION=$(python -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')
PYTHON_VERSION_INFO=(${PYTHON_VERSION//./ })

coverage erase

cov exporter/oxeye_opentelemetry-exporter-datadog
cov instrumentation/oxeye_opentelemetry-instrumentation-flask
cov instrumentation/oxeye_opentelemetry-instrumentation-requests
cov instrumentation/oxeye_opentelemetry-instrumentation-wsgi
cov instrumentation/oxeye_opentelemetry-instrumentation-aiohttp-client
cov instrumentation/oxeye_opentelemetry-instrumentation-asgi


coverage report --show-missing
coverage xml
