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

"""High level end-to-end test of the generate content instrumentation.

The primary purpose of this test is to verify that the instrumentation
package does not break the underlying GenAI SDK that it instruments.

This test suite also has some minimal validation of the instrumentation
outputs; however, validating the instrumentation output (other than
verifying that instrumentation does not break the GenAI SDK) is a
secondary goal of this test. Detailed testing of the instrumentation
output is the purview of the other tests in this directory."""

import google.genai
from google.genai import types as genai_types
import os
import vcr
from vcr.record_mode import RecordMode
import logging
import asyncio
import pytest

from ..common.auth import FakeCredentials
from ..common.otel_mocker import OTelMocker

from opentelemetry.instrumentation.google_genai import (
    GoogleGenAiSdkInstrumentor,
)


def _should_redact_header(header_key):
    if header_key.startswith('x-goog'):
        return True
    if header_key.startswith('sec-goog'):
        return True
    return False


def _redact_headers(headers):
    for header_key in headers:
        if _should_redact_header(header_key.lower()):
            del headers[header_key]


def _before_record_request(request):
    _redact_headers(request.headers)
    return request


def _before_record_response(response):
    _redact_headers(response.headers)
    return response


@pytest.fixture(scope='module')
def vcr_config():
    return {
        'filter_query_parameters': [
            'key',
            'apiKey',
            'quotaUser',
            'userProject',
            'token',
            'access_token',
            'accessToken',
            'refesh_token',
            'refreshToken',
            'authuser',
            'bearer',
            'bearer_token',
            'bearerToken',
            'userIp',
        ],
        'filter_post_data_parameters': [
            'apikey',
            'api_key',
            'key'
        ],
        'filter_headers': [
            'authorization',
        ],
        'before_record_request': _before_record_request,
        'before_record_response': _before_record_response,
    }


@pytest.fixture
def instrumentor():
    return GoogleGenAiSdkInstrumentor()


@pytest.fixture(autouse=True)
def setup_instrumentation(instrumentor):
    instrumentor.instrument()
    yield
    instrumentor.uninstrument()


@pytest.fixture(autouse=True)
def otel_mocker():
    result = OTelMocker()
    result.install()
    yield result
    result.uninstall()


@pytest.fixture(autouse=True, params=[True, False])
def setup_content_recording(request):
    os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = str(request.param)


@pytest.fixture
def vcr_record_mode(vcr):
    return vcr.record_mode


@pytest.fixture
def in_replay_mode(vcr_record_mode):
    return vcr_record_mode == RecordMode.NONE


@pytest.fixture
def gcloud_project(in_replay_mode):
    if in_replay_mode:
        return "test-project"
    _, from_creds = google.auth.default()
    return from_creds
    

@pytest.fixture
def gcloud_location(in_replay_mode):
    if in_replay_mode:
        return "test-location"
    return os.getenv("GCLOUD_LOCATION")


@pytest.fixture
def gcloud_credentials(in_replay_mode):
    if in_replay_mode:
        return FakeCredentials()
    creds, _ = google.auth.default()
    return creds


@pytest.fixture(autouse=True)
def gcloud_api_key(in_replay_mode):
    if in_replay_mode:
        os.environ["GOOGLE_API_KEY"] = "test-api-key"
        return "test-api-key"
    return os.getenv("GOOGLE_API_KEY")


@pytest.fixture
def nonvertex_client_factory(gcloud_api_key):
    def _factory():
        return google.genai.Client(api_key=gcloud_api_key)
    return _factory


@pytest.fixture
def vertex_client_factory(in_replay_mode):
    def _factory():
        return google.genai.Client(
            vertexai=True,
            project=gcloud_project,
            location=gcloud_location,
            credentials=gcloud_credentials)
    return _factory


@pytest.fixture(params=[True, False])
def use_vertex(request):
    return request.param


@pytest.fixture
def client(vertex_client_factory, nonvertex_client_factory, use_vertex):
    if use_vertex:
        return vertex_client_factory()
    return nonvertex_client_factory()


@pytest.fixture(params=[True, False])
def is_async(request):
    return request.param


@pytest.fixture(params=["gemini-1.0-flash", "gemini-2.0-flash"])
def model(request):
    return request.param


@pytest.fixture
def generate_content(client, is_async):
    def _sync_impl(*args, **kwargs):
        return client.models.generate_content(*args, **kwargs)

    def _async_impl(*args, **kwargs):
        return asyncio.run(client.aio.models.generate_content(*args, **kwargs))

    if is_async:
        return _async_impl
    return _sync_impl


@pytest.fixture
def generate_content_stream(client, is_async):
    def _sync_impl(*args, **kwargs):
        results = []
        for result in client.models.generate_content_stream(*args, **kwargs):
            results.append(result)
        return results

    def _async_impl(*args, **kwargs):
        async def _gather_all():
            results = []
            async for result in await client.aio.models.generate_content_stream(*args, **kwargs):
                results.append(result)
            return results
        return asyncio.run(_gather_all())

    if is_async:
        return _async_impl
    return _sync_impl


@pytest.mark.vcr
def test_single_response(generate_content, model, otel_mocker):
    response = generate_content(
        model=model,
        contents="Create a poem about Open Telemetry.")
    assert response is not None
    assert response.text is not None
    assert len(response.text) > 0
    otel_mocker.assert_has_span_named(f"generate_content {model}")


@pytest.mark.vcr
def test_multiple_responses(generate_content_stream, model, otel_mocker):
    count = 0
    for response in generate_content_stream(
            model=model,
            contents="Create a poem about Open Telemetry.",
            config=genai_types.GenerateContentConfig(candidate_count=2)):
        assert response is not None
        assert response.text is not None
        assert len(response.text) > 0
        count += 1
    assert count == 2
    otel_mocker.assert_has_span_named(f"generate_content {model}")
