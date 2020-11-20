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

from typing import Dict, Sequence

from opentelemetry.exporter.prometheus_remote_write.gen.types_pb2 import (
    Label,
    Sample,
    TimeSeries,
)
from opentelemetry.sdk.metrics.export import (
    ExportRecord,
    MetricsExporter,
    MetricsExportResult,
)


class PrometheusRemoteWriteMetricsExporter(MetricsExporter):
    """
    Prometheus remote write metric exporter for OpenTelemetry.

    Args:
        endpoint: url where data will be sent (Required)
        basic_auth: username and password for authentication (Optional)
        bearer_token: token used for authentication (Optional)
        bearer_token_file: filepath to file containing authentication token (Optional)
        headers: additional headers for remote write request (Optional
    """

    def __init__(
        self,
        endpoint: str,
        basic_auth: Dict = None,
        bearer_token: str = None,
        bearer_token_file: str = None,
        headers: Dict = None,
    ):
        self.endpoint = endpoint
        if basic_auth:
            self.basic_auth = basic_auth
        if bearer_token:
            self.bearer_token = bearer_token
        if bearer_token_file:
            self.bearer_token_file = bearer_token_file
        if headers:
            self.headers = headers

    @property
    def endpoint(self):
        return self._endpoint

    @endpoint.setter
    def endpoint(self, endpoint: str):
        if endpoint == "":
            raise ValueError("endpoint required")
        self._endpoint = endpoint

    @property
    def basic_auth(self):
        return self._basic_auth

    @basic_auth.setter
    def basic_auth(self, basic_auth: Dict):
        if hasattr(self, "bearer_token") or hasattr(self, "bearer_token_file"):
            raise ValueError("cannot contain basic_auth and bearer_token")
        if "username" not in basic_auth:
            raise ValueError("username required in basic_auth")
        if "password" not in basic_auth and "password_file" not in basic_auth:
            raise ValueError("password required in basic_auth")
        if "password" in basic_auth and "password_file" in basic_auth:
            raise ValueError(
                "basic_auth cannot contain password and password_file"
            )
        self._basic_auth = basic_auth

    @property
    def bearer_token(self):
        return self._bearer_token

    @bearer_token.setter
    def bearer_token(self, bearer_token: str):
        if hasattr(self, "basic_auth"):
            raise ValueError("cannot contain basic_auth and bearer_token")
        if hasattr(self, "bearer_token_file"):
            raise ValueError(
                "cannot contain bearer_token and bearer_token_file"
            )
        self._bearer_token = bearer_token

    @property
    def bearer_token_file(self):
        return self._bearer_token_file

    @bearer_token_file.setter
    def bearer_token_file(self, bearer_token_file: str):
        if hasattr(self, "basic_auth"):
            raise ValueError("cannot contain basic_auth and bearer_token")
        if hasattr(self, "bearer_token"):
            raise ValueError(
                "cannot contain bearer_token and bearer_token_file"
            )
        self._bearer_token_file = bearer_token_file

    @property
    def headers(self):
        return self._headers

    @headers.setter
    def headers(self, headers: Dict):
        self._headers = headers

    def export(
        self, export_records: Sequence[ExportRecord]
    ) -> MetricsExportResult:
        raise NotImplementedError()

    def shutdown(self) -> None:
        raise NotImplementedError()

    def convert_to_timeseries(
        self, export_records: Sequence[ExportRecord]
    ) -> Sequence[TimeSeries]:
        raise NotImplementedError()

    def convert_from_sum(self, sum_record: ExportRecord) -> TimeSeries:
        raise NotImplementedError()

    def convert_from_min_max_sum_count(
        self, min_max_sum_count_record: ExportRecord
    ) -> TimeSeries:
        raise NotImplementedError()

    def convert_from_histogram(
        self, histogram_record: ExportRecord
    ) -> TimeSeries:
        raise NotImplementedError()

    def convert_from_last_value(
        self, last_value_record: ExportRecord
    ) -> TimeSeries:
        raise NotImplementedError()

    def convert_from_value_observer(
        self, value_observer_record: ExportRecord
    ) -> TimeSeries:
        raise NotImplementedError()

    def convert_from_quantile(
        self, summary_record: ExportRecord
    ) -> TimeSeries:
        raise NotImplementedError()

    # pylint: disable=no-member
    def create_timeseries(
        self, export_record: ExportRecord, name, value: float
    ) -> TimeSeries:
        raise NotImplementedError()

    def create_sample(self, timestamp: int, value: float) -> Sample:
        raise NotImplementedError()

    def create_label(self, name: str, value: str) -> Label:
        raise NotImplementedError()

    def build_message(self, timeseries: Sequence[TimeSeries]) -> bytes:
        raise NotImplementedError()

    def get_headers(self) -> Dict:
        raise NotImplementedError()

    def send_message(
        self, message: bytes, headers: Dict
    ) -> MetricsExportResult:
        raise NotImplementedError()
