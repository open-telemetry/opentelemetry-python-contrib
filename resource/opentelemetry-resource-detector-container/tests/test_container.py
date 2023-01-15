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

from unittest.mock import mock_open, patch

from opentelemetry import trace as trace_api
from opentelemetry.resource.detector.container import ContainerResourceDetector
from opentelemetry.sdk.resources import get_aggregated_resources
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.test.wsgitestutil import WsgiTestBase

MockContainerResourceAttributes = {
    ResourceAttributes.CONTAINER_ID: "7be92808767a667f35c8505cbf40d14e931ef6db5b0210329cf193b15ba9d605",
}


def simple_wsgi(environ, start_response):
    start_response("200 OK", [("Content-Type", "text/plain")])

    def response():
        yield b"*"
    return response()


class ContainerResourceDetectorTest(WsgiTestBase):
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data=f"""14:name=systemd:/docker/{MockContainerResourceAttributes[ResourceAttributes.CONTAINER_ID]}
        13:rdma:/
        12:pids:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
        11:hugetlb:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
        10:net_prio:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
        9:perf_event:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
        8:net_cls:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
        7:freezer:/docker/
        6:devices:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
        5:memory:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
        4:blkio:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
        3:cpuacct:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
        2:cpu:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
        1:cpuset:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
        """,
    )
    def test_container_id_detect_from_cgroup_file(self, mock_cgroup_file):
        actual = ContainerResourceDetector().detect()
        self.assertDictEqual(actual.attributes.copy(), MockContainerResourceAttributes)

    @patch(
        "opentelemetry.resource.detector.container.ContainerResourceDetector._get_container_id_v1",
        return_value=MockContainerResourceAttributes[ResourceAttributes.CONTAINER_ID],
    )
    def test_container_id_as_span_attribute(self, mock_cgroup_file):
        tracer_provider, exporter = self.create_tracer_provider(
            resource=get_aggregated_resources(
                [
                    ContainerResourceDetector()
                ]
            )
        )
        tracer = tracer_provider.get_tracer(__name__)

        with tracer.start_as_current_span(
            "test", kind=trace_api.SpanKind.SERVER
        ) as _:
            response = simple_wsgi(self.environ, self.start_response)
            while True:
                try:
                    value = next(response)
                    self.assertEqual(value, b"*")
                except StopIteration:
                    break

        span_list = exporter.get_finished_spans()
        self.assertEqual(
            span_list[0].resource.attributes["container.id"],
            MockContainerResourceAttributes[ResourceAttributes.CONTAINER_ID]
        )

    @patch(
        "opentelemetry.resource.detector.container.ContainerResourceDetector._get_container_id_v1",
        return_value=MockContainerResourceAttributes[ResourceAttributes.CONTAINER_ID],
    )
    def test_container_id_detect_from_cgroup(self, mock_get_container_id_v1):
        actual = ContainerResourceDetector().detect()
        self.assertDictEqual(actual.attributes.copy(), MockContainerResourceAttributes)

    @patch(
        "opentelemetry.resource.detector.container.ContainerResourceDetector._get_container_id_v1",
        return_value=None,
    )
    @patch(
        "opentelemetry.resource.detector.container.ContainerResourceDetector._get_container_id_v2",
        return_value=MockContainerResourceAttributes[ResourceAttributes.CONTAINER_ID],
    )
    def test_container_id_detect_from_mount_info(
        self,
        mock_get_container_id_v1,
        mock_get_container_id_v2
    ):
        actual = ContainerResourceDetector().detect()
        self.assertDictEqual(actual.attributes.copy(), MockContainerResourceAttributes)
