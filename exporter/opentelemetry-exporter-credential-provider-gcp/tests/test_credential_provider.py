# Copyright 2023 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from os import environ
from unittest import TestCase
from unittest.mock import MagicMock, patch

from google.auth.transport.requests import AuthorizedSession

from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.sdk.environment_variables import (
    _OTEL_PYTHON_EXPORTER_OTLP_GRPC_TRACES_CREDENTIAL_PROVIDER,
    _OTEL_PYTHON_EXPORTER_OTLP_HTTP_TRACES_CREDENTIAL_PROVIDER,
)

# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportMissingImports=false


class TestOTLPTraceAutoInstrumentGcpCredential(TestCase):
    @patch("google.auth.default")
    @patch.dict(
        environ,
        {
            _OTEL_PYTHON_EXPORTER_OTLP_HTTP_TRACES_CREDENTIAL_PROVIDER: "gcp_http_credentials",
            _OTEL_PYTHON_EXPORTER_OTLP_GRPC_TRACES_CREDENTIAL_PROVIDER: "gcp_grpc_credentials",
        },
    )
    def test_loads_otlp_exporters_with_google_creds(
        self, mock_default: MagicMock
    ):  # pylint: disable=no-self-use
        """Test that OTel configuration internals can load the credentials from entrypoint by
        name"""
        mock_credentials = MagicMock()
        mock_credentials.project_id = "test-project"
        mock_default.return_value = (mock_credentials, "test-project")
        http_exporter = OTLPSpanExporter()
        assert isinstance(http_exporter._session, AuthorizedSession)
        # Assert that google.auth.default was called
        mock_default.assert_called_once()
