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
from opentelemetry.test.test_base import TestBase

MockContainerResourceAttributes = {
    ResourceAttributes.CONTAINER_ID: "7be92808767a667f35c8505cbf40d14e931ef6db5b0210329cf193b15ba9d605",
}


class ContainerResourceDetectorTest(TestBase):
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
        self.assertDictEqual(
            actual.attributes.copy(), MockContainerResourceAttributes
        )

    @patch(
        "opentelemetry.resource.detector.container._get_container_id_v1",
        return_value=None,
    )
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data=f"""
            608 607 0:183 / /proc rw,nosuid,nodev,noexec,relatime - proc proc rw
            609 607 0:184 / /dev rw,nosuid - tmpfs tmpfs rw,size=65536k,mode=755
            610 609 0:185 / /dev/pts rw,nosuid,noexec,relatime - devpts devpts rw,gid=5,mode=620,ptmxmode=666
            611 607 0:186 / /sys ro,nosuid,nodev,noexec,relatime - sysfs sysfs ro
            612 611 0:29 / /sys/fs/cgroup ro,nosuid,nodev,noexec,relatime - cgroup2 cgroup rw
            613 609 0:182 / /dev/mqueue rw,nosuid,nodev,noexec,relatime - mqueue mqueue rw
            614 609 0:187 / /dev/shm rw,nosuid,nodev,noexec,relatime - tmpfs shm rw,size=65536k
            615 607 254:1 /docker/containers/{MockContainerResourceAttributes[ResourceAttributes.CONTAINER_ID]}/resolv.conf /etc/resolv.conf rw,relatime - ext4 /dev/vda1 rw
            616 607 254:1 /docker/containers/{MockContainerResourceAttributes[ResourceAttributes.CONTAINER_ID]}/hostname /etc/hostname rw,relatime - ext4 /dev/vda1 rw
            617 607 254:1 /docker/containers/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked/hosts /etc/hosts rw,relatime - ext4 /dev/vda1 rw
            618 607 0:131 /Users/sankmeht/development/otel/opentelemetry-python /development/otel/opentelemetry-python rw,nosuid,nodev,relatime - fuse.grpcfuse grpcfuse rw,user_id=0,group_id=0,allow_other,max_read=1048576
            619 607 0:131 /Users/sankmeht/development/otel/opentelemetry-python-contrib /development/otel/opentelemetry-python-contrib rw,nosuid,nodev,relatime - fuse.grpcfuse grpcfuse rw,user_id=0,group_id=0,allow_other,max_read=1048576
            519 609 0:185 /0 /dev/console rw,nosuid,noexec,relatime - devpts devpts rw,gid=5,mode=620,ptmxmode=666
            520 608 0:183 /bus /proc/bus ro,nosuid,nodev,noexec,relatime - proc proc rw
            521 608 0:183 /fs /proc/fs ro,nosuid,nodev,noexec,relatime - proc proc rw
            522 608 0:183 /irq /proc/irq ro,nosuid,nodev,noexec,relatime - proc proc rw
            523 608 0:183 /sys /proc/sys ro,nosuid,nodev,noexec,relatime - proc proc rw
            524 608 0:183 /sysrq-trigger /proc/sysrq-trigger ro,nosuid,nodev,noexec,relatime - proc proc rw
            525 608 0:212 / /proc/acpi ro,relatime - tmpfs tmpfs ro
            526 608 0:184 /null /proc/kcore rw,nosuid - tmpfs tmpfs rw,size=65536k,mode=755
            527 608 0:184 /null /proc/keys rw,nosuid - tmpfs tmpfs rw,size=65536k,mode=755
            528 608 0:184 /null /proc/timer_list rw,nosuid - tmpfs tmpfs rw,size=65536k,mode=755
            529 611 0:213 / /sys/firmware ro,relatime - tmpfs tmpfs ro
            """,
    )
    def test_container_id_detect_from_mountinfo_file(
        self, mock_get_container_id_v1, mock_cgroup_file
    ):
        actual = ContainerResourceDetector().detect()
        self.assertDictEqual(
            actual.attributes.copy(), MockContainerResourceAttributes
        )

    @patch(
        "opentelemetry.resource.detector.container._get_container_id",
        return_value=MockContainerResourceAttributes[
            ResourceAttributes.CONTAINER_ID
        ],
    )
    def test_container_id_as_span_attribute(self, mock_cgroup_file):
        tracer_provider, exporter = self.create_tracer_provider(
            resource=get_aggregated_resources([ContainerResourceDetector()])
        )
        tracer = tracer_provider.get_tracer(__name__)

        with tracer.start_as_current_span(
            "test", kind=trace_api.SpanKind.SERVER
        ) as _:
            pass

        span_list = exporter.get_finished_spans()
        self.assertEqual(
            span_list[0].resource.attributes["container.id"],
            MockContainerResourceAttributes[ResourceAttributes.CONTAINER_ID],
        )

    @patch(
        "opentelemetry.resource.detector.container._get_container_id",
        return_value=MockContainerResourceAttributes[
            ResourceAttributes.CONTAINER_ID
        ],
    )
    def test_container_id_detect_from_cgroup(self, mock_get_container_id):
        actual = ContainerResourceDetector().detect()
        self.assertDictEqual(
            actual.attributes.copy(), MockContainerResourceAttributes
        )

    @patch(
        "opentelemetry.resource.detector.container._get_container_id_v1",
        return_value=None,
    )
    @patch(
        "opentelemetry.resource.detector.container._get_container_id_v2",
        return_value=MockContainerResourceAttributes[
            ResourceAttributes.CONTAINER_ID
        ],
    )
    def test_container_id_detect_from_mount_info(
        self, mock_get_container_id_v1, mock_get_container_id_v2
    ):
        actual = ContainerResourceDetector().detect()
        self.assertDictEqual(
            actual.attributes.copy(), MockContainerResourceAttributes
        )
