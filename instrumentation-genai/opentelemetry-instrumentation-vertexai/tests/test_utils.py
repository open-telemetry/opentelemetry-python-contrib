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


from google.cloud.aiplatform_v1.types import (
    content,
)
from google.cloud.aiplatform_v1beta1.types import (
    content as content_v1beta1,
)

from opentelemetry.instrumentation.vertexai.utils import (
    _map_finish_reason,
    get_server_attributes,
)


def test_get_server_attributes() -> None:
    # without port
    assert get_server_attributes("us-central1-aiplatform.googleapis.com") == {
        "server.address": "us-central1-aiplatform.googleapis.com",
        "server.port": 443,
    }

    # with port
    assert get_server_attributes(
        "us-central1-aiplatform.googleapis.com:5432"
    ) == {
        "server.address": "us-central1-aiplatform.googleapis.com",
        "server.port": 5432,
    }


def test_map_finish_reason():
    for Enum in (
        content.Candidate.FinishReason,
        content_v1beta1.Candidate.FinishReason,
    ):
        for finish_reason, expect in [
            # Handled mappings
            (Enum.FINISH_REASON_UNSPECIFIED, "error"),
            (Enum.OTHER, "error"),
            (Enum.STOP, "stop"),
            (Enum.MAX_TOKENS, "length"),
            # Preserve vertex enum value
            (Enum.BLOCKLIST, "BLOCKLIST"),
            (Enum.MALFORMED_FUNCTION_CALL, "MALFORMED_FUNCTION_CALL"),
            (Enum.PROHIBITED_CONTENT, "PROHIBITED_CONTENT"),
            (Enum.RECITATION, "RECITATION"),
            (Enum.SAFETY, "SAFETY"),
            (Enum.SPII, "SPII"),
        ]:
            assert _map_finish_reason(finish_reason) == expect
