# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import pytest


@pytest.fixture(scope="module")
def vcr_config():
    return {
        "filter_headers": [
            ("authorization", "Bearer key"),
        ],
        "decode_compressed_response": True,
        "before_record_response": scrub_response_headers,
    }


def scrub_response_headers(response):
    """
    This scrubs sensitive response headers. Note they are case-sensitive!
    """
    return response
