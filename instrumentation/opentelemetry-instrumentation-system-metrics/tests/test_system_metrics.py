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

# pylint: disable=protected-access,too-many-lines

import sys
from collections import namedtuple
from platform import python_implementation
from unittest import mock, skipIf

from opentelemetry.instrumentation.system_metrics import (
    _DEFAULT_CONFIG,
    SystemMetricsInstrumentor,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.test.test_base import TestBase


def _mock_netconnection():
    NetConnection = namedtuple(
        "NetworkConnection", ["family", "type", "status"]
    )
    Type = namedtuple("Type", ["value"])
    return [
        NetConnection(
            family=1,
            status="ESTABLISHED",
            type=Type(value=2),
        ),
        NetConnection(
            family=1,
            status="ESTABLISHED",
            type=Type(value=1),
        ),
    ]


class _SystemMetricsResult:
    def __init__(self, attributes, value) -> None:
        self.attributes = attributes
        self.value = value


# pylint:disable=too-many-public-methods
class TestSystemMetrics(TestBase):
    def setUp(self):
        super().setUp()
        self.implementation = python_implementation().lower()
        self._patch_net_connections = mock.patch(
            "psutil.net_connections", _mock_netconnection
        )
        self._patch_net_connections.start()

        # Reset the singleton class on each test run
        SystemMetricsInstrumentor._instance = None

    def tearDown(self):
        super().tearDown()
        self._patch_net_connections.stop()
        SystemMetricsInstrumentor().uninstrument()

    def test_system_metrics_instrumentor_initialization(self):
        try:
            SystemMetricsInstrumentor()
            SystemMetricsInstrumentor(config={})
        except Exception as error:  # pylint: disable=broad-except
            self.fail(f"Unexpected exception {error} raised")

        SystemMetricsInstrumentor._instance = None

        try:
            SystemMetricsInstrumentor(config={})
            SystemMetricsInstrumentor()
        except Exception as error:  # pylint: disable=broad-except
            self.fail(f"Unexpected exception {error} raised")

        SystemMetricsInstrumentor().instrument()

    def test_system_metrics_instrument(self):
        reader = InMemoryMetricReader()
        meter_provider = MeterProvider(metric_readers=[reader])
        system_metrics = SystemMetricsInstrumentor()
        system_metrics.instrument(meter_provider=meter_provider)
        metric_names = []
        for resource_metrics in reader.get_metrics_data().resource_metrics:
            for scope_metrics in resource_metrics.scope_metrics:
                for metric in scope_metrics.metrics:
                    metric_names.append(metric.name)

        observer_names = [
            "system.cpu.time",
            "system.cpu.utilization",
            "system.memory.usage",
            "system.memory.utilization",
            "system.swap.usage",
            "system.swap.utilization",
            "system.disk.io",
            "system.disk.operations",
            "system.disk.time",
            "system.network.dropped_packets",
            "system.network.packets",
            "system.network.errors",
            "system.network.io",
            "system.network.connections",
            "system.thread_count",
            "process.context_switches",
            "process.cpu.time",
            "process.cpu.utilization",
            "process.memory.usage",
            "process.memory.virtual",
            "process.thread.count",
            f"process.runtime.{self.implementation}.memory",
            f"process.runtime.{self.implementation}.cpu_time",
            f"process.runtime.{self.implementation}.thread_count",
            f"process.runtime.{self.implementation}.context_switches",
            f"process.runtime.{self.implementation}.cpu.utilization",
        ]

        # platform dependent metrics
        if sys.platform != "win32":
            observer_names.append(
                "process.open_file_descriptor.count",
            )
        if self.implementation != "pypy":
            observer_names.append(
                f"process.runtime.{self.implementation}.gc_count",
            )

        self.assertEqual(sorted(metric_names), sorted(observer_names))

    def test_process_metrics_instrument(self):
        process_config = {
            "process.context_switches": ["involuntary", "voluntary"],
            "process.cpu.time": ["user", "system"],
            "process.cpu.utilization": None,
            "process.memory.usage": None,
            "process.memory.virtual": None,
            "process.open_file_descriptor.count": None,
            "process.thread.count": None,
        }

        reader = InMemoryMetricReader()
        meter_provider = MeterProvider(metric_readers=[reader])
        process_metrics = SystemMetricsInstrumentor(config=process_config)
        process_metrics.instrument(meter_provider=meter_provider)

        metric_names = []
        for resource_metrics in reader.get_metrics_data().resource_metrics:
            for scope_metrics in resource_metrics.scope_metrics:
                for metric in scope_metrics.metrics:
                    metric_names.append(metric.name)

        observer_names = [
            "process.memory.usage",
            "process.memory.virtual",
            "process.cpu.time",
            "process.thread.count",
            "process.context_switches",
            "process.cpu.utilization",
        ]
        # platform dependent metrics
        if sys.platform != "win32":
            observer_names.append(
                "process.open_file_descriptor.count",
            )

        self.assertEqual(sorted(metric_names), sorted(observer_names))

    def test_runtime_metrics_instrument(self):
        runtime_config = {
            "process.runtime.memory": ["rss", "vms"],
            "process.runtime.cpu.time": ["user", "system"],
            "process.runtime.thread_count": None,
            "process.runtime.cpu.utilization": None,
            "process.runtime.context_switches": ["involuntary", "voluntary"],
        }

        if self.implementation != "pypy":
            runtime_config["process.runtime.gc_count"] = None

        reader = InMemoryMetricReader()
        meter_provider = MeterProvider(metric_readers=[reader])
        runtime_metrics = SystemMetricsInstrumentor(config=runtime_config)
        runtime_metrics.instrument(meter_provider=meter_provider)

        metric_names = []
        for resource_metrics in reader.get_metrics_data().resource_metrics:
            for scope_metrics in resource_metrics.scope_metrics:
                for metric in scope_metrics.metrics:
                    metric_names.append(metric.name)

        observer_names = [
            f"process.runtime.{self.implementation}.memory",
            f"process.runtime.{self.implementation}.cpu_time",
            f"process.runtime.{self.implementation}.thread_count",
            f"process.runtime.{self.implementation}.context_switches",
            f"process.runtime.{self.implementation}.cpu.utilization",
        ]
        if self.implementation != "pypy":
            observer_names.append(
                f"process.runtime.{self.implementation}.gc_count"
            )

        self.assertEqual(sorted(metric_names), sorted(observer_names))

    def _assert_metrics(self, observer_name, reader, expected):
        assertions = 0
        # pylint: disable=too-many-nested-blocks
        for resource_metrics in reader.get_metrics_data().resource_metrics:
            for scope_metrics in resource_metrics.scope_metrics:
                for metric in scope_metrics.metrics:
                    for data_point in metric.data.data_points:
                        for expect in expected:
                            if (
                                dict(data_point.attributes)
                                == expect.attributes
                                and metric.name == observer_name
                            ):
                                self.assertEqual(
                                    data_point.value,
                                    expect.value,
                                )
                                assertions += 1
        self.assertEqual(len(expected), assertions)

    @staticmethod
    def _setup_instrumentor() -> InMemoryMetricReader:
        reader = InMemoryMetricReader()
        meter_provider = MeterProvider(metric_readers=[reader])

        system_metrics = SystemMetricsInstrumentor()
        system_metrics.instrument(meter_provider=meter_provider)
        return reader

    def _test_metrics(self, observer_name, expected):
        reader = self._setup_instrumentor()
        self._assert_metrics(observer_name, reader, expected)

    def _assert_metrics_not_found(self, observer_name):
        reader = self._setup_instrumentor()
        seen_metrics = set()
        for resource_metrics in reader.get_metrics_data().resource_metrics:
            for scope_metrics in resource_metrics.scope_metrics:
                for metric in scope_metrics.metrics:
                    seen_metrics.add(metric.name)
        self.assertNotIn(observer_name, seen_metrics)

    # This patch is added here to stop psutil from raising an exception
    # because we're patching cpu_times
    # pylint: disable=unused-argument
    @mock.patch("psutil.cpu_times_percent")
    @mock.patch("psutil.cpu_times")
    def test_system_cpu_time(self, mock_cpu_times, mock_cpu_times_percent):
        CPUTimes = namedtuple("CPUTimes", ["idle", "user", "system", "irq"])
        mock_cpu_times.return_value = [
            CPUTimes(idle=1.2, user=3.4, system=5.6, irq=7.8),
            CPUTimes(idle=1.2, user=3.4, system=5.6, irq=7.8),
        ]

        expected = [
            _SystemMetricsResult(
                {
                    "cpu": 1,
                    "state": "idle",
                },
                1.2,
            ),
            _SystemMetricsResult(
                {
                    "cpu": 1,
                    "state": "user",
                },
                3.4,
            ),
            _SystemMetricsResult(
                {
                    "cpu": 1,
                    "state": "system",
                },
                5.6,
            ),
            _SystemMetricsResult(
                {
                    "cpu": 1,
                    "state": "irq",
                },
                7.8,
            ),
            _SystemMetricsResult(
                {
                    "cpu": 2,
                    "state": "idle",
                },
                1.2,
            ),
            _SystemMetricsResult(
                {
                    "cpu": 2,
                    "state": "user",
                },
                3.4,
            ),
            _SystemMetricsResult(
                {
                    "cpu": 2,
                    "state": "system",
                },
                5.6,
            ),
            _SystemMetricsResult(
                {
                    "cpu": 2,
                    "state": "irq",
                },
                7.8,
            ),
        ]
        self._test_metrics("system.cpu.time", expected)

    @mock.patch("psutil.cpu_times_percent")
    def test_system_cpu_utilization(self, mock_cpu_times_percent):
        CPUTimesPercent = namedtuple(
            "CPUTimesPercent", ["idle", "user", "system", "irq"]
        )
        mock_cpu_times_percent.return_value = [
            CPUTimesPercent(idle=1.2, user=3.4, system=5.6, irq=7.8),
            CPUTimesPercent(idle=1.2, user=3.4, system=5.6, irq=7.8),
        ]

        expected = [
            _SystemMetricsResult({"cpu": 1, "state": "idle"}, 1.2 / 100),
            _SystemMetricsResult({"cpu": 1, "state": "user"}, 3.4 / 100),
            _SystemMetricsResult({"cpu": 1, "state": "system"}, 5.6 / 100),
            _SystemMetricsResult({"cpu": 1, "state": "irq"}, 7.8 / 100),
            _SystemMetricsResult({"cpu": 2, "state": "idle"}, 1.2 / 100),
            _SystemMetricsResult({"cpu": 2, "state": "user"}, 3.4 / 100),
            _SystemMetricsResult({"cpu": 2, "state": "system"}, 5.6 / 100),
            _SystemMetricsResult({"cpu": 2, "state": "irq"}, 7.8 / 100),
        ]
        self._test_metrics("system.cpu.utilization", expected)

    @mock.patch("psutil.virtual_memory")
    def test_system_memory_usage(self, mock_virtual_memory):
        VirtualMemory = namedtuple(
            "VirtualMemory", ["used", "free", "cached", "total"]
        )
        mock_virtual_memory.return_value = VirtualMemory(
            used=1, free=2, cached=3, total=4
        )

        expected = [
            _SystemMetricsResult({"state": "used"}, 1),
            _SystemMetricsResult({"state": "free"}, 2),
            _SystemMetricsResult({"state": "cached"}, 3),
        ]
        self._test_metrics("system.memory.usage", expected)

    @mock.patch("psutil.virtual_memory")
    def test_system_memory_utilization(self, mock_virtual_memory):
        VirtualMemory = namedtuple(
            "VirtualMemory", ["used", "free", "cached", "total"]
        )
        mock_virtual_memory.return_value = VirtualMemory(
            used=1, free=2, cached=3, total=4
        )

        expected = [
            _SystemMetricsResult({"state": "used"}, 1 / 4),
            _SystemMetricsResult({"state": "free"}, 2 / 4),
            _SystemMetricsResult({"state": "cached"}, 3 / 4),
        ]
        self._test_metrics("system.memory.utilization", expected)

    @mock.patch("psutil.swap_memory")
    def test_system_swap_usage(self, mock_swap_memory):
        SwapMemory = namedtuple("SwapMemory", ["used", "free", "total"])
        mock_swap_memory.return_value = SwapMemory(used=1, free=2, total=3)

        expected = [
            _SystemMetricsResult({"state": "used"}, 1),
            _SystemMetricsResult({"state": "free"}, 2),
        ]
        self._test_metrics("system.swap.usage", expected)

    @mock.patch("psutil.swap_memory")
    def test_system_swap_utilization(self, mock_swap_memory):
        SwapMemory = namedtuple("SwapMemory", ["used", "free", "total"])
        mock_swap_memory.return_value = SwapMemory(used=1, free=2, total=3)

        expected = [
            _SystemMetricsResult({"state": "used"}, 1 / 3),
            _SystemMetricsResult({"state": "free"}, 2 / 3),
        ]
        self._test_metrics("system.swap.utilization", expected)

    @mock.patch("psutil.disk_io_counters")
    def test_system_disk_io(self, mock_disk_io_counters):
        DiskIO = namedtuple(
            "DiskIO",
            [
                "read_count",
                "write_count",
                "read_bytes",
                "write_bytes",
                "read_time",
                "write_time",
                "read_merged_count",
                "write_merged_count",
            ],
        )
        mock_disk_io_counters.return_value = {
            "sda": DiskIO(
                read_count=1,
                write_count=2,
                read_bytes=3,
                write_bytes=4,
                read_time=5,
                write_time=6,
                read_merged_count=7,
                write_merged_count=8,
            ),
            "sdb": DiskIO(
                read_count=9,
                write_count=10,
                read_bytes=11,
                write_bytes=12,
                read_time=13,
                write_time=14,
                read_merged_count=15,
                write_merged_count=16,
            ),
        }

        expected = [
            _SystemMetricsResult({"device": "sda", "direction": "read"}, 3),
            _SystemMetricsResult({"device": "sda", "direction": "write"}, 4),
            _SystemMetricsResult({"device": "sdb", "direction": "read"}, 11),
            _SystemMetricsResult({"device": "sdb", "direction": "write"}, 12),
        ]
        self._test_metrics("system.disk.io", expected)

    @mock.patch("psutil.disk_io_counters")
    def test_system_disk_operations(self, mock_disk_io_counters):
        DiskIO = namedtuple(
            "DiskIO",
            [
                "read_count",
                "write_count",
                "read_bytes",
                "write_bytes",
                "read_time",
                "write_time",
                "read_merged_count",
                "write_merged_count",
            ],
        )
        mock_disk_io_counters.return_value = {
            "sda": DiskIO(
                read_count=1,
                write_count=2,
                read_bytes=3,
                write_bytes=4,
                read_time=5,
                write_time=6,
                read_merged_count=7,
                write_merged_count=8,
            ),
            "sdb": DiskIO(
                read_count=9,
                write_count=10,
                read_bytes=11,
                write_bytes=12,
                read_time=13,
                write_time=14,
                read_merged_count=15,
                write_merged_count=16,
            ),
        }

        expected = [
            _SystemMetricsResult({"device": "sda", "direction": "read"}, 1),
            _SystemMetricsResult({"device": "sda", "direction": "write"}, 2),
            _SystemMetricsResult({"device": "sdb", "direction": "read"}, 9),
            _SystemMetricsResult({"device": "sdb", "direction": "write"}, 10),
        ]
        self._test_metrics("system.disk.operations", expected)

    @mock.patch("psutil.disk_io_counters")
    def test_system_disk_time(self, mock_disk_io_counters):
        DiskIO = namedtuple(
            "DiskIO",
            [
                "read_count",
                "write_count",
                "read_bytes",
                "write_bytes",
                "read_time",
                "write_time",
                "read_merged_count",
                "write_merged_count",
            ],
        )
        mock_disk_io_counters.return_value = {
            "sda": DiskIO(
                read_count=1,
                write_count=2,
                read_bytes=3,
                write_bytes=4,
                read_time=5,
                write_time=6,
                read_merged_count=7,
                write_merged_count=8,
            ),
            "sdb": DiskIO(
                read_count=9,
                write_count=10,
                read_bytes=11,
                write_bytes=12,
                read_time=13,
                write_time=14,
                read_merged_count=15,
                write_merged_count=16,
            ),
        }

        expected = [
            _SystemMetricsResult(
                {"device": "sda", "direction": "read"}, 5 / 1000
            ),
            _SystemMetricsResult(
                {"device": "sda", "direction": "write"}, 6 / 1000
            ),
            _SystemMetricsResult(
                {"device": "sdb", "direction": "read"}, 13 / 1000
            ),
            _SystemMetricsResult(
                {"device": "sdb", "direction": "write"}, 14 / 1000
            ),
        ]
        self._test_metrics("system.disk.time", expected)

    @mock.patch("psutil.net_io_counters")
    def test_system_network_dropped_packets(self, mock_net_io_counters):
        NetIO = namedtuple(
            "NetIO",
            [
                "dropin",
                "dropout",
                "packets_sent",
                "packets_recv",
                "errin",
                "errout",
                "bytes_sent",
                "bytes_recv",
            ],
        )
        mock_net_io_counters.return_value = {
            "eth0": NetIO(
                dropin=1,
                dropout=2,
                packets_sent=3,
                packets_recv=4,
                errin=5,
                errout=6,
                bytes_sent=7,
                bytes_recv=8,
            ),
            "eth1": NetIO(
                dropin=9,
                dropout=10,
                packets_sent=11,
                packets_recv=12,
                errin=13,
                errout=14,
                bytes_sent=15,
                bytes_recv=16,
            ),
        }

        expected = [
            _SystemMetricsResult(
                {"device": "eth0", "direction": "receive"}, 1
            ),
            _SystemMetricsResult(
                {"device": "eth0", "direction": "transmit"}, 2
            ),
            _SystemMetricsResult(
                {"device": "eth1", "direction": "receive"}, 9
            ),
            _SystemMetricsResult(
                {"device": "eth1", "direction": "transmit"}, 10
            ),
        ]
        self._test_metrics("system.network.dropped_packets", expected)

    @mock.patch("psutil.net_io_counters")
    def test_system_network_packets(self, mock_net_io_counters):
        NetIO = namedtuple(
            "NetIO",
            [
                "dropin",
                "dropout",
                "packets_sent",
                "packets_recv",
                "errin",
                "errout",
                "bytes_sent",
                "bytes_recv",
            ],
        )
        mock_net_io_counters.return_value = {
            "eth0": NetIO(
                dropin=1,
                dropout=2,
                packets_sent=3,
                packets_recv=4,
                errin=5,
                errout=6,
                bytes_sent=7,
                bytes_recv=8,
            ),
            "eth1": NetIO(
                dropin=9,
                dropout=10,
                packets_sent=11,
                packets_recv=12,
                errin=13,
                errout=14,
                bytes_sent=15,
                bytes_recv=16,
            ),
        }

        expected = [
            _SystemMetricsResult(
                {"device": "eth0", "direction": "receive"}, 4
            ),
            _SystemMetricsResult(
                {"device": "eth0", "direction": "transmit"}, 3
            ),
            _SystemMetricsResult(
                {"device": "eth1", "direction": "receive"}, 12
            ),
            _SystemMetricsResult(
                {"device": "eth1", "direction": "transmit"}, 11
            ),
        ]
        self._test_metrics("system.network.packets", expected)

    @mock.patch("psutil.net_io_counters")
    def test_system_network_errors(self, mock_net_io_counters):
        NetIO = namedtuple(
            "NetIO",
            [
                "dropin",
                "dropout",
                "packets_sent",
                "packets_recv",
                "errin",
                "errout",
                "bytes_sent",
                "bytes_recv",
            ],
        )
        mock_net_io_counters.return_value = {
            "eth0": NetIO(
                dropin=1,
                dropout=2,
                packets_sent=3,
                packets_recv=4,
                errin=5,
                errout=6,
                bytes_sent=7,
                bytes_recv=8,
            ),
            "eth1": NetIO(
                dropin=9,
                dropout=10,
                packets_sent=11,
                packets_recv=12,
                errin=13,
                errout=14,
                bytes_sent=15,
                bytes_recv=16,
            ),
        }

        expected = [
            _SystemMetricsResult(
                {"device": "eth0", "direction": "receive"}, 5
            ),
            _SystemMetricsResult(
                {"device": "eth0", "direction": "transmit"}, 6
            ),
            _SystemMetricsResult(
                {"device": "eth1", "direction": "receive"}, 13
            ),
            _SystemMetricsResult(
                {"device": "eth1", "direction": "transmit"}, 14
            ),
        ]
        self._test_metrics("system.network.errors", expected)

    @mock.patch("psutil.net_io_counters")
    def test_system_network_io(self, mock_net_io_counters):
        NetIO = namedtuple(
            "NetIO",
            [
                "dropin",
                "dropout",
                "packets_sent",
                "packets_recv",
                "errin",
                "errout",
                "bytes_sent",
                "bytes_recv",
            ],
        )
        mock_net_io_counters.return_value = {
            "eth0": NetIO(
                dropin=1,
                dropout=2,
                packets_sent=3,
                packets_recv=4,
                errin=5,
                errout=6,
                bytes_sent=7,
                bytes_recv=8,
            ),
            "eth1": NetIO(
                dropin=9,
                dropout=10,
                packets_sent=11,
                packets_recv=12,
                errin=13,
                errout=14,
                bytes_sent=15,
                bytes_recv=16,
            ),
        }

        expected = [
            _SystemMetricsResult(
                {"device": "eth0", "direction": "receive"}, 8
            ),
            _SystemMetricsResult(
                {"device": "eth0", "direction": "transmit"}, 7
            ),
            _SystemMetricsResult(
                {"device": "eth1", "direction": "receive"}, 16
            ),
            _SystemMetricsResult(
                {"device": "eth1", "direction": "transmit"}, 15
            ),
        ]
        self._test_metrics("system.network.io", expected)

    @mock.patch("psutil.net_connections")
    def test_system_network_connections(self, mock_net_connections):
        NetConnection = namedtuple(
            "NetworkConnection", ["family", "type", "status"]
        )
        Type = namedtuple("Type", ["value"])
        mock_net_connections.return_value = [
            NetConnection(
                family=1,
                status="ESTABLISHED",
                type=Type(value=2),
            ),
            NetConnection(
                family=1,
                status="ESTABLISHED",
                type=Type(value=1),
            ),
        ]

        expected = [
            _SystemMetricsResult(
                {
                    "family": 1,
                    "protocol": "udp",
                    "state": "ESTABLISHED",
                    "type": Type(value=2),
                },
                1,
            ),
            _SystemMetricsResult(
                {
                    "family": 1,
                    "protocol": "tcp",
                    "state": "ESTABLISHED",
                    "type": Type(value=1),
                },
                1,
            ),
        ]
        self._test_metrics("system.network.connections", expected)

    @mock.patch("threading.active_count")
    def test_system_thread_count(self, threading_active_count):
        threading_active_count.return_value = 42

        expected = [_SystemMetricsResult({}, 42)]
        self._test_metrics("system.thread_count", expected)

    @mock.patch("psutil.Process.memory_info")
    def test_memory_usage(self, mock_process_memory_info):
        PMem = namedtuple("PMem", ["rss", "vms"])

        mock_process_memory_info.configure_mock(
            **{"return_value": PMem(rss=1, vms=2)}
        )

        expected = [
            _SystemMetricsResult({}, 1),
        ]
        self._test_metrics("process.memory.usage", expected)

    @mock.patch("psutil.Process.memory_info")
    def test_memory_virtual(self, mock_process_memory_info):
        PMem = namedtuple("PMem", ["rss", "vms"])

        mock_process_memory_info.configure_mock(
            **{"return_value": PMem(rss=1, vms=2)}
        )

        expected = [
            _SystemMetricsResult({}, 2),
        ]
        self._test_metrics("process.memory.virtual", expected)

    @mock.patch("psutil.Process.cpu_times")
    def test_cpu_time(self, mock_process_cpu_times):
        PCPUTimes = namedtuple("PCPUTimes", ["user", "system"])

        mock_process_cpu_times.configure_mock(
            **{"return_value": PCPUTimes(user=1.1, system=2.2)}
        )

        expected = [
            _SystemMetricsResult({"type": "user"}, 1.1),
            _SystemMetricsResult({"type": "system"}, 2.2),
        ]
        self._test_metrics("process.cpu.time", expected)

    @mock.patch("psutil.Process.num_ctx_switches")
    def test_context_switches(self, mock_process_num_ctx_switches):
        PCtxSwitches = namedtuple("PCtxSwitches", ["voluntary", "involuntary"])

        mock_process_num_ctx_switches.configure_mock(
            **{"return_value": PCtxSwitches(voluntary=1, involuntary=2)}
        )

        expected = [
            _SystemMetricsResult({"type": "voluntary"}, 1),
            _SystemMetricsResult({"type": "involuntary"}, 2),
        ]
        self._test_metrics("process.context_switches", expected)

    @mock.patch("psutil.Process.num_ctx_switches")
    def test_context_switches_not_implemented_error(
        self, mock_process_num_ctx_switches
    ):
        mock_process_num_ctx_switches.side_effect = NotImplementedError

        self._assert_metrics_not_found("process.context_switches")

    @mock.patch("psutil.Process.num_threads")
    def test_thread_count(self, mock_process_thread_num):
        mock_process_thread_num.configure_mock(**{"return_value": 42})

        expected = [_SystemMetricsResult({}, 42)]
        self._test_metrics("process.thread.count", expected)

    @mock.patch("psutil.Process.cpu_percent")
    @mock.patch("psutil.cpu_count")
    def test_cpu_utilization(self, mock_cpu_count, mock_process_cpu_percent):
        mock_cpu_count.return_value = 1
        mock_process_cpu_percent.configure_mock(**{"return_value": 42})

        expected = [_SystemMetricsResult({}, 0.42)]
        self._test_metrics("process.cpu.utilization", expected)

    @skipIf(sys.platform == "win32", "No file descriptors on Windows")
    @mock.patch("psutil.Process.num_fds")
    def test_open_file_descriptor_count(self, mock_process_num_fds):
        mock_process_num_fds.configure_mock(**{"return_value": 3})

        expected = [_SystemMetricsResult({}, 3)]
        self._test_metrics(
            "process.open_file_descriptor.count",
            expected,
        )
        mock_process_num_fds.assert_called()

    @mock.patch("psutil.Process.memory_info")
    def test_runtime_memory(self, mock_process_memory_info):
        PMem = namedtuple("PMem", ["rss", "vms"])

        mock_process_memory_info.configure_mock(
            **{"return_value": PMem(rss=1, vms=2)}
        )

        expected = [
            _SystemMetricsResult({"type": "rss"}, 1),
            _SystemMetricsResult({"type": "vms"}, 2),
        ]
        self._test_metrics(
            f"process.runtime.{self.implementation}.memory", expected
        )

    @mock.patch("psutil.Process.cpu_times")
    def test_runtime_cpu_time(self, mock_process_cpu_times):
        PCPUTimes = namedtuple("PCPUTimes", ["user", "system"])

        mock_process_cpu_times.configure_mock(
            **{"return_value": PCPUTimes(user=1.1, system=2.2)}
        )

        expected = [
            _SystemMetricsResult({"type": "user"}, 1.1),
            _SystemMetricsResult({"type": "system"}, 2.2),
        ]
        self._test_metrics(
            f"process.runtime.{self.implementation}.cpu_time", expected
        )

    @mock.patch("gc.get_count")
    @skipIf(
        python_implementation().lower() == "pypy", "not supported for pypy"
    )
    def test_runtime_get_count(self, mock_gc_get_count):
        mock_gc_get_count.configure_mock(**{"return_value": (1, 2, 3)})

        expected = [
            _SystemMetricsResult({"count": "0"}, 1),
            _SystemMetricsResult({"count": "1"}, 2),
            _SystemMetricsResult({"count": "2"}, 3),
        ]
        self._test_metrics(
            f"process.runtime.{self.implementation}.gc_count", expected
        )

    @mock.patch("psutil.Process.num_ctx_switches")
    def test_runtime_context_switches(self, mock_process_num_ctx_switches):
        PCtxSwitches = namedtuple("PCtxSwitches", ["voluntary", "involuntary"])

        mock_process_num_ctx_switches.configure_mock(
            **{"return_value": PCtxSwitches(voluntary=1, involuntary=2)}
        )

        expected = [
            _SystemMetricsResult({"type": "voluntary"}, 1),
            _SystemMetricsResult({"type": "involuntary"}, 2),
        ]
        self._test_metrics(
            f"process.runtime.{self.implementation}.context_switches", expected
        )

    @mock.patch("psutil.Process.num_ctx_switches")
    def test_runtime_context_switches_not_implemented_error(
        self, mock_process_num_ctx_switches
    ):
        mock_process_num_ctx_switches.side_effect = NotImplementedError

        self._assert_metrics_not_found(
            f"process.runtime.{self.implementation}.context_switches",
        )

    @mock.patch("psutil.Process.num_threads")
    def test_runtime_thread_count(self, mock_process_thread_num):
        mock_process_thread_num.configure_mock(**{"return_value": 42})

        expected = [_SystemMetricsResult({}, 42)]
        self._test_metrics(
            f"process.runtime.{self.implementation}.thread_count", expected
        )

    @mock.patch("psutil.Process.cpu_percent")
    def test_runtime_cpu_utilization(self, mock_process_cpu_percent):
        mock_process_cpu_percent.configure_mock(**{"return_value": 42})

        expected = [_SystemMetricsResult({}, 0.42)]
        self._test_metrics(
            f"process.runtime.{self.implementation}.cpu.utilization", expected
        )


class TestConfigSystemMetrics(TestBase):
    # pylint:disable=no-self-use
    def test_that_correct_config_is_read(self):
        for key, value in _DEFAULT_CONFIG.items():
            meter_provider = MeterProvider([InMemoryMetricReader()])
            instrumentor = SystemMetricsInstrumentor(config={key: value})
            instrumentor.instrument(meter_provider=meter_provider)
            meter_provider.force_flush()
            instrumentor.uninstrument()
