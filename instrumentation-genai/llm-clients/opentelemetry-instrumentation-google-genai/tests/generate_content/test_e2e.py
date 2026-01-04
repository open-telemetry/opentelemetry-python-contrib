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

import asyncio
import gzip
import json
import os
import subprocess
import sys
import time

import fsspec
import google.auth
import google.auth.credentials
import google.genai
import pytest
import yaml
from google.genai import types
from vcr.record_mode import RecordMode

from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
    _OpenTelemetryStabilitySignalType,
    _StabilityMode,
)
from opentelemetry.instrumentation.google_genai import (
    GoogleGenAiSdkInstrumentor,
)
from opentelemetry.util.genai.environment_variables import (
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT,
    OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH,
)

from ..common.auth import FakeCredentials
from ..common.otel_mocker import OTelMocker

_FAKE_PROJECT = "test-project"
_FAKE_LOCATION = "test-location"
_FAKE_API_KEY = "test-api-key"
_DEFAULT_REAL_LOCATION = "us-central1"


def _get_project_from_env():
    return (
        os.getenv("GCLOUD_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT") or ""
    )


def _get_project_from_gcloud_cli():
    try:
        gcloud_call_result = subprocess.run(
            "gcloud config get project",
            shell=True,
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        return None
    gcloud_output = gcloud_call_result.stdout.decode()
    return gcloud_output.strip()


def _get_project_from_credentials():
    _, from_creds = google.auth.default()
    return from_creds


def _get_real_project():
    from_env = _get_project_from_env()
    if from_env:
        return from_env
    from_cli = _get_project_from_gcloud_cli()
    if from_cli:
        return from_cli
    return _get_project_from_credentials()


def _get_location_from_env():
    return (
        os.getenv("GCLOUD_LOCATION")
        or os.getenv("GOOGLE_CLOUD_LOCATION")
        or ""
    )


def _get_real_location():
    return _get_location_from_env() or _DEFAULT_REAL_LOCATION


def _get_vertex_api_key_from_env():
    return os.getenv("GOOGLE_API_KEY")


def _get_gemini_api_key_from_env():
    return os.getenv("GEMINI_API_KEY")


def _should_redact_header(header_key):
    if header_key.startswith("x-goog"):
        return True
    if header_key.startswith("sec-goog"):
        return True
    if header_key in ["server", "server-timing"]:
        return True
    return False


def _redact_headers(headers):
    for header_key in headers:
        if _should_redact_header(header_key.lower()):
            headers[header_key] = "<REDACTED>"


def _before_record_request(request):
    if request.headers:
        _redact_headers(request.headers)
    uri = request.uri
    project = _get_project_from_env()
    if project:
        uri = uri.replace(f"projects/{project}", f"projects/{_FAKE_PROJECT}")
    location = _get_real_location()
    if location:
        uri = uri.replace(
            f"locations/{location}", f"locations/{_FAKE_LOCATION}"
        )
        uri = uri.replace(
            f"//{location}-aiplatform.googleapis.com",
            f"//{_FAKE_LOCATION}-aiplatform.googleapis.com",
        )
    request.uri = uri
    return request


def _before_record_response(response):
    if hasattr(response, "headers") and response.headers:
        _redact_headers(response.headers)
    return response


@pytest.fixture(name="vcr_config", scope="module")
def fixture_vcr_config():
    return {
        "filter_query_parameters": [
            "key",
            "apiKey",
            "quotaUser",
            "userProject",
            "token",
            "access_token",
            "accessToken",
            "refesh_token",
            "refreshToken",
            "authuser",
            "bearer",
            "bearer_token",
            "bearerToken",
            "userIp",
        ],
        "filter_post_data_parameters": ["apikey", "api_key", "key"],
        "filter_headers": [
            "x-goog-api-key",
            "authorization",
            "server",
            "Server",
            "Server-Timing",
            "Date",
        ],
        "before_record_request": _before_record_request,
        "before_record_response": _before_record_response,
        "ignore_hosts": [
            "oauth2.googleapis.com",
            "iam.googleapis.com",
        ],
    }


class _LiteralBlockScalar(str):
    """Formats the string as a literal block scalar, preserving whitespace and
    without interpreting escape characters"""


def _literal_block_scalar_presenter(dumper, data):
    """Represents a scalar string as a literal block, via '|' syntax"""
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")


@pytest.fixture(
    name="internal_setup_yaml_pretty_formatting", scope="module", autouse=True
)
def fixture_setup_yaml_pretty_formatting():
    yaml.add_representer(_LiteralBlockScalar, _literal_block_scalar_presenter)


def _process_string_value(string_value):
    """Pretty-prints JSON or returns long strings as a LiteralBlockScalar"""
    try:
        json_data = json.loads(string_value)
        return _LiteralBlockScalar(json.dumps(json_data, indent=2))
    except (ValueError, TypeError):
        if len(string_value) > 80:
            return _LiteralBlockScalar(string_value)
    return string_value


def _convert_body_to_literal(data):
    """Searches the data for body strings, attempting to pretty-print JSON"""
    if isinstance(data, dict):
        for key, value in data.items():
            # Handle response body case (e.g., response.body.string)
            if key == "body" and isinstance(value, dict) and "string" in value:
                value["string"] = _process_string_value(value["string"])

            # Handle request body case (e.g., request.body)
            elif key == "body" and isinstance(value, str):
                data[key] = _process_string_value(value)

            else:
                _convert_body_to_literal(value)

    elif isinstance(data, list):
        for idx, choice in enumerate(data):
            data[idx] = _convert_body_to_literal(choice)

    return data


# Helper for enforcing GZIP compression where it was originally.
def _ensure_gzip_single_response(data: bytes):
    try:
        # Attempt to decompress, first, to avoid double compression.
        gzip.decompress(data)
        return data
    except gzip.BadGzipFile:
        # It must not have been compressed in the first place.
        return gzip.compress(data)


# VCRPy automatically decompresses responses before saving them, but it may forget to
# re-encode them when the data is loaded. This can create issues with decompression.
# This is why we re-encode on load; to accurately replay what was originally sent.
#
# https://vcrpy.readthedocs.io/en/latest/advanced.html#decode-compressed-response
def _ensure_casette_gzip(loaded_casette):
    for interaction in loaded_casette["interactions"]:
        response = interaction["response"]
        headers = response["headers"]
        if (
            "content-encoding" not in headers
            and "Content-Encoding" not in headers
        ):
            continue
        if (
            "content-encoding" in headers
            and "gzip" not in headers["content-encoding"]
        ):
            continue
        if (
            "Content-Encoding" in headers
            and "gzip" not in headers["Content-Encoding"]
        ):
            continue
        response["body"]["string"] = _ensure_gzip_single_response(
            response["body"]["string"].encode()
        )


def _maybe_ensure_casette_gzip(result):
    if sys.version_info[0] == 3 and sys.version_info[1] == 9:
        _ensure_casette_gzip(result)


class _PrettyPrintJSONBody:
    """This makes request and response body recordings more readable."""

    @staticmethod
    def serialize(cassette_dict):
        cassette_dict = _convert_body_to_literal(cassette_dict)
        return yaml.dump(
            cassette_dict, default_flow_style=False, allow_unicode=True
        )

    @staticmethod
    def deserialize(cassette_string):
        result = yaml.load(cassette_string, Loader=yaml.Loader)
        _maybe_ensure_casette_gzip(result)
        return result


@pytest.fixture(name="fully_initialized_vcr", scope="module", autouse=True)
def setup_vcr(vcr):
    vcr.register_serializer("yaml", _PrettyPrintJSONBody)
    vcr.serializer = "yaml"
    return vcr


@pytest.fixture(name="instrumentor")
def fixture_instrumentor():
    return GoogleGenAiSdkInstrumentor()


@pytest.fixture(name="enable_completion_hook")
def fixture_enable_completion_hook(request):
    return getattr(request, "param", "default")


@pytest.fixture(name="semconv_version")
def fixture_semconv_version(request):
    return getattr(request, "param", "default")


@pytest.fixture(name="internal_instrumentation_setup", autouse=True)
def fixture_setup_instrumentation(instrumentor, enable_completion_hook):
    if enable_completion_hook == "enable_completion_hook":
        os.environ.update(
            {
                OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH: "memory://",
                "OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK": "upload",
            }
        )
    instrumentor.instrument()
    yield
    instrumentor.uninstrument()


@pytest.fixture(name="otel_mocker", autouse=True)
def fixture_otel_mocker():
    result = OTelMocker()
    result.install()
    yield result
    result.uninstall()


@pytest.fixture(
    name="setup_content_recording",
    autouse=True,
    params=["logcontent", "excludecontent"],
)
def fixture_setup_content_recording(request, semconv_version):
    enabled = request.param == "logcontent"
    # due to some init weirdness, this needs to be updated manually to work, and later restored,
    # otherwise, state of this dict leaks to other tests and breaks them.
    orig_dict = _OpenTelemetrySemanticConventionStability._OTEL_SEMCONV_STABILITY_SIGNAL_MAPPING.copy()
    if semconv_version == "experimental":
        capture_content = "SPAN_AND_EVENT" if enabled else "NO_CONTENT"
        os.environ.update(
            {
                OTEL_SEMCONV_STABILITY_OPT_IN: "gen_ai_latest_experimental",
                OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: capture_content,
            }
        )
        _OpenTelemetrySemanticConventionStability._OTEL_SEMCONV_STABILITY_SIGNAL_MAPPING.update(
            {
                _OpenTelemetryStabilitySignalType.GEN_AI: _StabilityMode.GEN_AI_LATEST_EXPERIMENTAL
            }
        )
    else:
        os.environ[OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT] = str(
            enabled
        )
    yield
    _OpenTelemetrySemanticConventionStability._OTEL_SEMCONV_STABILITY_SIGNAL_MAPPING = orig_dict


@pytest.fixture(name="vcr_record_mode")
def fixture_vcr_record_mode(vcr):
    return vcr.record_mode


@pytest.fixture(name="in_replay_mode")
def fixture_in_replay_mode(vcr_record_mode):
    return vcr_record_mode == RecordMode.NONE


@pytest.fixture(name="gcloud_project", autouse=True)
def fixture_gcloud_project(in_replay_mode):
    if in_replay_mode:
        return _FAKE_PROJECT
    result = _get_real_project()
    for env_var in ["GCLOUD_PROJECT", "GOOGLE_CLOUD_PROJECT"]:
        os.environ[env_var] = result
    return result


@pytest.fixture(name="gcloud_location")
def fixture_gcloud_location(in_replay_mode):
    if in_replay_mode:
        return _FAKE_LOCATION
    return _get_real_location()


@pytest.fixture(name="gcloud_credentials")
def fixture_gcloud_credentials(in_replay_mode):
    if in_replay_mode:
        return FakeCredentials()
    creds, _ = google.auth.default()
    return google.auth.credentials.with_scopes_if_required(
        creds, ["https://www.googleapis.com/auth/cloud-platform"]
    )


@pytest.fixture(name="gemini_api_key")
def fixture_gemini_api_key(in_replay_mode):
    if in_replay_mode:
        return _FAKE_API_KEY
    return os.getenv("GEMINI_API_KEY")


@pytest.fixture(name="gcloud_api_key", autouse=True)
def fixture_gcloud_api_key(gemini_api_key):
    if "GOOGLE_API_KEY" not in os.environ:
        os.environ["GOOGLE_API_KEY"] = gemini_api_key
    return os.getenv("GOOGLE_API_KEY")


@pytest.fixture(name="nonvertex_client_factory")
def fixture_nonvertex_client_factory(gemini_api_key):
    def _factory():
        return google.genai.Client(
            api_key=gemini_api_key,
            vertexai=False,
            http_options=types.HttpOptions(
                # to prevent compression
                headers={"accept-encoding": "identity"}
            ),
        )

    return _factory


@pytest.fixture(name="vertex_client_factory")
def fixture_vertex_client_factory(
    gcloud_project, gcloud_location, gcloud_credentials
):
    def _factory():
        return google.genai.Client(
            vertexai=True,
            project=gcloud_project,
            location=gcloud_location,
            credentials=gcloud_credentials,
            http_options=types.HttpOptions(
                headers={"accept-encoding": "identity"}
            ),
        )

    return _factory


@pytest.fixture(name="genai_sdk_backend", params=["vertexaiapi"])
def fixture_genai_sdk_backend(request):
    return request.param


@pytest.fixture(name="use_vertex", autouse=True)
def fixture_use_vertex(genai_sdk_backend):
    result = bool(genai_sdk_backend == "vertexaiapi")
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "1" if result else "0"
    return result


@pytest.fixture(name="client")
def fixture_client(
    vertex_client_factory, nonvertex_client_factory, use_vertex
):
    if use_vertex:
        return vertex_client_factory()
    return nonvertex_client_factory()


@pytest.fixture(name="is_async", params=["sync", "async"])
def fixture_is_async(request):
    return request.param == "async"


@pytest.fixture(name="model", params=["gemini-2.5-flash"])
def fixture_model(request):
    return request.param


@pytest.fixture(name="generate_content")
def fixture_generate_content(client, is_async):
    def _sync_impl(*args, **kwargs):
        return client.models.generate_content(*args, **kwargs)

    def _async_impl(*args, **kwargs):
        return asyncio.run(client.aio.models.generate_content(*args, **kwargs))

    if is_async:
        return _async_impl
    return _sync_impl


@pytest.fixture(name="generate_content_stream")
def fixture_generate_content_stream(client, is_async):
    def _sync_impl(*args, **kwargs):
        results = []
        for result in client.models.generate_content_stream(*args, **kwargs):
            results.append(result)
        return results

    def _async_impl(*args, **kwargs):
        async def _gather_all():
            results = []
            async for (
                result
            ) in await client.aio.models.generate_content_stream(
                *args, **kwargs
            ):
                results.append(result)
            return results

        return asyncio.run(_gather_all())

    if is_async:
        return _async_impl
    return _sync_impl


@pytest.mark.parametrize("semconv_version", ["default"], indirect=True)
@pytest.mark.vcr
def test_non_streaming(generate_content, model, otel_mocker):
    response = generate_content(
        model=model, contents="Create a poem about Open Telemetry."
    )
    assert response is not None
    assert response.text is not None
    assert len(response.text) > 0
    otel_mocker.assert_has_span_named(f"generate_content {model}")


@pytest.mark.parametrize("semconv_version", ["default"], indirect=True)
@pytest.mark.vcr
def test_streaming(generate_content_stream, model, otel_mocker):
    count = 0
    for response in generate_content_stream(
        model=model, contents="Create a poem about Open Telemetry."
    ):
        assert response is not None
        assert response.text is not None
        assert len(response.text) > 0
        count += 1
    assert count > 0
    otel_mocker.assert_has_span_named(f"generate_content {model}")


@pytest.mark.parametrize("semconv_version", ["experimental"], indirect=True)
@pytest.mark.parametrize(
    "enable_completion_hook", ["enable_completion_hook"], indirect=True
)
@pytest.mark.vcr
def test_upload_hook_non_streaming(
    generate_content, model, otel_mocker: OTelMocker
):
    expected_input = [
        {
            "parts": [
                {
                    "content": "Create a haiku about Open Telemetry.",
                    "type": "text",
                }
            ],
            "role": "user",
        }
    ]
    expected_output = [
        {
            "role": "assistant",
            "parts": [
                {
                    "content": "Open data streams,\nMetrics, logs, and traces flow,\nClearly see inside.",
                    "type": "text",
                }
            ],
            "finish_reason": "stop",
        }
    ]
    _ = generate_content(
        model=model, contents="Create a haiku about Open Telemetry."
    )
    time.sleep(2)

    event = otel_mocker.get_event_named(
        "gen_ai.client.inference.operation.details"
    )
    assert_fsspec_equal(
        event.attributes["gen_ai.input.messages_ref"], expected_input
    )

    span = otel_mocker.get_span_named(f"generate_content {model}")
    assert_fsspec_equal(
        span.attributes["gen_ai.output.messages_ref"], expected_output
    )


def assert_fsspec_equal(path, value):
    # Hide this function and its calls from traceback.
    __tracebackhide__ = True  # pylint: disable=unused-variable
    with fsspec.open(path, "r") as file:
        assert json.load(file) == value
