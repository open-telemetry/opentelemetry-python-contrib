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

import unittest
from collections import OrderedDict
from unittest.mock import mock_open, patch
import pytest

from opentelemetry.resource.detector.kubernetes import (
    KubernetesResourceDetector,
    get_kubenertes_pod_uid_v1,
    get_kubenertes_pod_uid_v2
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes

MockKubernetesResourceAttributes = {
    ResourceAttributes.K8S_POD_UID: "ecc2f8af-7742-4087-aeb1-4601bf25e1df",
}



class KubernetesResourceDetectorTest(unittest.TestCase):
    @patch(
        "opentelemetry.resource.detector.kubernetes.get_kubenertes_pod_uid_v1",
         return_value=f"{MockKubernetesResourceAttributes[ResourceAttributes.K8S_POD_UID]}",
    )
    @patch(
        "opentelemetry.resource.detector.kubernetes.get_kubenertes_pod_uid_v2",
         return_value=f"{MockKubernetesResourceAttributes[ResourceAttributes.K8S_POD_UID]}",
    )
    def test_simple_detector(
        self, mock_get_kubenertes_pod_uid_v1, mock_get_kubenertes_pod_uid_v2
    ):
        actual = KubernetesResourceDetector().detect()
        self.assertEqual(
            actual.attributes[ResourceAttributes.K8S_POD_UID],
            MockKubernetesResourceAttributes[ResourceAttributes.K8S_POD_UID]
        )

    @patch(
        "opentelemetry.resource.detector.kubernetes.get_kubenertes_pod_uid_v1",
        side_effect=Exception('Test')
    )
    def test_without_container(
        self, mock_get_kubenertes_pod_uid_v1):
        actual = KubernetesResourceDetector().detect()
        self.assertEqual(Resource.get_empty(), actual)
    
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data=f"""564 446 0:164 / / rw,relatime master:190 - overlay overlay rw,lowerdir=/var/lib/docker/bogusPodIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
565 564 0:166 / /proc rw,nosuid,nodev,noexec,relatime - proc proc rw
566 564 0:338 / /dev rw,nosuid - tmpfs tmpfs rw,size=65536k,mode=755
567 566 0:339 / /dev/pts rw,nosuid,noexec,relatime - devpts devpts rw,gid=5,mode=620,ptmxmode=666
568 564 0:161 / /sys ro,nosuid,nodev,noexec,relatime - sysfs sysfs ro
569 568 0:30 / /sys/fs/cgroup ro,nosuid,nodev,noexec,relatime - cgroup2 cgroup rw
570 566 0:157 / /dev/mqueue rw,nosuid,nodev,noexec,relatime - mqueue mqueue rw
571 566 254:1 /docker/volumes/minikube/_data/lib/kubelet/pods/{MockKubernetesResourceAttributes[ResourceAttributes.K8S_POD_UID]}/containers/my-shell/0447d6c5 /dev/termination-log rw,relatime - ext4 /dev/vda1 rw
572 564 254:1 /docker/volumes/minikube/_data/lib/docker/containers/bogusPodIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
573 564 254:1 /docker/volumes/minikube/_data/lib/docker/containers/bogusPodIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
574 564 254:1 /docker/volumes/minikube/_data/lib/kubelet/pods/{MockKubernetesResourceAttributes[ResourceAttributes.K8S_POD_UID]}/etc-hosts /etc/hosts rw,relatime - ext4 /dev/vda1 rw
575 566 0:156 / /bogusPodIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
576 564 0:153 / /bogusPodIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
447 566 0:339 /0 /bogusPodIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
448 565 0:166 /bus /bogusPodIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
450 565 0:166 /irq /bogusPodIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
451 565 0:166 /sys /bogusPodIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
452 565 0:166 /sysrq-trigger /bogusPodIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
""",
    )
    def test_get_kubenertes_pod_uid_v1(
        self, mock_open
    ):
        actual_pod_uid = get_kubenertes_pod_uid_v1()
        self.assertEqual(
            actual_pod_uid, 
            MockKubernetesResourceAttributes[ResourceAttributes.K8S_POD_UID]
        )
    
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data=f"""14:name=systemd:/docker/c24aa3879860ee981d29f0492aef1e39c45d7c7fcdff7bd2050047d0bd390311/kubepods/besteffort/pod{MockKubernetesResourceAttributes[ResourceAttributes.K8S_POD_UID]}/bogusPodIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
13:rdma:/kubepods/besteffort/pod{MockKubernetesResourceAttributes[ResourceAttributes.K8S_POD_UID]}/bogusPodIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
12:pids:/docker/c24aa3879860ee981d29f0492aef1e39c45d7c7fcdff7bd2050047d0bd390311/kubepods/besteffort/pod{MockKubernetesResourceAttributes[ResourceAttributes.K8S_POD_UID]}/bogusPodIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
11:hugetlb:/docker/c24aa3879860ee981d29f0492aef1e39c45d7c7fcdff7bd2050047d0bd390311/kubepods/besteffort/pod{MockKubernetesResourceAttributes[ResourceAttributes.K8S_POD_UID]}/bogusPodIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
10:net_prio:/docker/c24aa3879860ee981d29f0492aef1e39c45d7c7fcdff7bd2050047d0bd390311/kubepods/besteffort/pod{MockKubernetesResourceAttributes[ResourceAttributes.K8S_POD_UID]}/bogusPodIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
9:perf_event:/docker/c24aa3879860ee981d29f0492aef1e39c45d7c7fcdff7bd2050047d0bd390311/kubepods/besteffort/pod{MockKubernetesResourceAttributes[ResourceAttributes.K8S_POD_UID]}/bogusPodIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
8:net_cls:/docker/c24aa3879860ee981d29f0492aef1e39c45d7c7fcdff7bd2050047d0bd390311/kubepods/besteffort/pod{MockKubernetesResourceAttributes[ResourceAttributes.K8S_POD_UID]}/bogusPodIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
7:freezer:/docker/c24aa3879860ee981d29f0492aef1e39c45d7c7fcdff7bd2050047d0bd390311/kubepods/besteffort/pod{MockKubernetesResourceAttributes[ResourceAttributes.K8S_POD_UID]}/bogusPodIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
6:devices:/docker/c24aa3879860ee981d29f0492aef1e39c45d7c7fcdff7bd2050047d0bd390311/kubepods/besteffort/pod{MockKubernetesResourceAttributes[ResourceAttributes.K8S_POD_UID]}/bogusPodIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
5:memory:/docker/c24aa3879860ee981d29f0492aef1e39c45d7c7fcdff7bd2050047d0bd390311/kubepods/besteffort/pod{MockKubernetesResourceAttributes[ResourceAttributes.K8S_POD_UID]}/bogusPodIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
4:blkio:/docker/c24aa3879860ee981d29f0492aef1e39c45d7c7fcdff7bd2050047d0bd390311/kubepods/besteffort/pod{MockKubernetesResourceAttributes[ResourceAttributes.K8S_POD_UID]}/bogusPodIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
3:cpuacct:/docker/c24aa3879860ee981d29f0492aef1e39c45d7c7fcdff7bd2050047d0bd390311/kubepods/besteffort/pod{MockKubernetesResourceAttributes[ResourceAttributes.K8S_POD_UID]}/bogusPodIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
2:cpu:/docker/c24aa3879860ee981d29f0492aef1e39c45d7c7fcdff7bd2050047d0bd390311/kubepods/besteffort/pod{MockKubernetesResourceAttributes[ResourceAttributes.K8S_POD_UID]}/bogusPodIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
1:cpuset:/docker/c24aa3879860ee981d29f0492aef1e39c45d7c7fcdff7bd2050047d0bd390311/kubepods/besteffort/pod{MockKubernetesResourceAttributes[ResourceAttributes.K8S_POD_UID]}/bogusPodIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
0::/kubepods/besteffort/pod{MockKubernetesResourceAttributes[ResourceAttributes.K8S_POD_UID]}/bogusPodIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
""",
    )
    def test_get_kubenertes_pod_uid_v2(
        self, mock_open
    ):
        actual_pod_uid = get_kubenertes_pod_uid_v2()
        self.assertEqual(
            actual_pod_uid, 
            MockKubernetesResourceAttributes[ResourceAttributes.K8S_POD_UID]
        )
    

