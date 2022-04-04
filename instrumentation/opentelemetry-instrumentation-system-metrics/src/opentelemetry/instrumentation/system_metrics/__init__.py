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
"""
Instrument to report system (CPU, memory, network) and
process (CPU, memory, garbage collection) metrics. By default, the
following metrics are configured:

.. code:: python

    {
        "system.cpu.time": ["idle", "user", "system", "irq"],
        "system.cpu.utilization": ["idle", "user", "system", "irq"],
        "system.memory.usage": ["used", "free", "cached"],
        "system.memory.utilization": ["used", "free", "cached"],
        "system.swap.usage": ["used", "free"],
        "system.swap.utilization": ["used", "free"],
        "system.disk.io": ["read", "write"],
        "system.disk.operations": ["read", "write"],
        "system.disk.time": ["read", "write"],
        "system.network.dropped.packets": ["transmit", "receive"],
        "system.network.packets": ["transmit", "receive"],
        "system.network.errors": ["transmit", "receive"],
        "system.network.io": ["trasmit", "receive"],
        "system.network.connections": ["family", "type"],
        "runtime.memory": ["rss", "vms"],
        "runtime.cpu.time": ["user", "system"],
    }

Usage
-----

.. code:: python

    from opentelemetry._metrics import set_meter_provider
    from opentelemetry.instrumentation.system_metrics import SystemMetricsInstrumentor
    from opentelemetry.sdk._metrics import MeterProvider
    from opentelemetry.sdk._metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader

    exporter = ConsoleMetricExporter()

    set_meter_provider(MeterProvider(PeriodicExportingMetricReader(exporter)))
    SystemMetricsInstrumentor().instrument()

    # metrics are collected asynchronously
    input("...")

    # to configure custom metrics
    configuration = {
        "system.memory.usage": ["used", "free", "cached"],
        "system.cpu.time": ["idle", "user", "system", "irq"],
        "system.network.io": ["trasmit", "receive"],
        "runtime.memory": ["rss", "vms"],
        "runtime.cpu.time": ["user", "system"],
    }
    SystemMetricsInstrumentor(config=configuration).instrument()

API
---
"""

from typing import Collection

import gc
import os
from typing import Dict, List, Iterable, Optional
from platform import python_implementation

import psutil

from opentelemetry._metrics import get_meter
from opentelemetry._metrics.measurement import Measurement
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.system_metrics.version import __version__
from opentelemetry.instrumentation.system_metrics.package import _instruments
from opentelemetry.sdk.util import get_dict_as_key


class SystemMetricsInstrumentor(BaseInstrumentor):
    # pylint: disable=too-many-statements
    def __init__(
        self,
        labels: Optional[Dict[str, str]] = None,
        config: Optional[Dict[str, List[str]]] = None,
    ):
        super().__init__()
        if config is None:
            self._config = {
                "system.cpu.time": ["idle", "user", "system", "irq"],
                "system.cpu.utilization": ["idle", "user", "system", "irq"],
                "system.memory.usage": ["used", "free", "cached"],
                "system.memory.utilization": ["used", "free", "cached"],
                "system.swap.usage": ["used", "free"],
                "system.swap.utilization": ["used", "free"],
                # system.swap.page.faults: [],
                # system.swap.page.operations: [],
                "system.disk.io": ["read", "write"],
                "system.disk.operations": ["read", "write"],
                "system.disk.time": ["read", "write"],
                # "system.filesystem.usage": [],
                # "system.filesystem.utilization": [],
                "system.network.dropped.packets": ["transmit", "receive"],
                "system.network.packets": ["transmit", "receive"],
                "system.network.errors": ["transmit", "receive"],
                "system.network.io": ["trasmit", "receive"],
                "system.network.connections": ["family", "type"],
                "runtime.memory": ["rss", "vms"],
                "runtime.cpu.time": ["user", "system"],
            }
        else:
            self._config = config
        self._labels = {} if labels is None else labels
        self._meter = None

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        meter_provider = kwargs.get("meter_provider")
        self._meter = get_meter(
            "io.otel.python.instrumentation.system_metrics",
            __version__,
            meter_provider,
        )
        self._python_implementation = python_implementation().lower()

        self._proc = psutil.Process(os.getpid())

        self._system_cpu_time_labels = self._labels.copy()
        self._system_cpu_utilization_labels = self._labels.copy()

        self._system_memory_usage_labels = self._labels.copy()
        self._system_memory_utilization_labels = self._labels.copy()

        self._system_swap_usage_labels = self._labels.copy()
        self._system_swap_utilization_labels = self._labels.copy()
        # self._system_swap_page_faults = self._labels.copy()
        # self._system_swap_page_operations = self._labels.copy()

        self._system_disk_io_labels = self._labels.copy()
        self._system_disk_operations_labels = self._labels.copy()
        self._system_disk_time_labels = self._labels.copy()
        self._system_disk_merged_labels = self._labels.copy()

        # self._system_filesystem_usage_labels = self._labels.copy()
        # self._system_filesystem_utilization_labels = self._labels.copy()

        self._system_network_dropped_packets_labels = self._labels.copy()
        self._system_network_packets_labels = self._labels.copy()
        self._system_network_errors_labels = self._labels.copy()
        self._system_network_io_labels = self._labels.copy()
        self._system_network_connections_labels = self._labels.copy()

        self._runtime_memory_labels = self._labels.copy()
        self._runtime_cpu_time_labels = self._labels.copy()
        self._runtime_gc_count_labels = self._labels.copy()

        self._meter.create_observable_counter(
            callback=self._get_system_cpu_time,
            name="system.cpu.time",
            description="System CPU time",
            unit="seconds",
        )

        self._meter.create_observable_gauge(
            callback=self._get_system_cpu_utilization,
            name="system.cpu.utilization",
            description="System CPU utilization",
            unit="1",
        )

        self._meter.create_observable_gauge(
            callback=self._get_system_memory_usage,
            name="system.memory.usage",
            description="System memory usage",
            unit="bytes",
        )

        self._meter.create_observable_gauge(
            callback=self._get_system_memory_utilization,
            name="system.memory.utilization",
            description="System memory utilization",
            unit="1",
        )

        self._meter.create_observable_gauge(
            callback=self._get_system_swap_usage,
            name="system.swap.usage",
            description="System swap usage",
            unit="pages",
        )

        self._meter.create_observable_gauge(
            callback=self._get_system_swap_utilization,
            name="system.swap.utilization",
            description="System swap utilization",
            unit="1",
        )

        # # self._meter.create_observable_counter(
        # #     callback=self._get_system_swap_page_faults,
        # #     name="system.swap.page_faults",
        # #     description="System swap page faults",
        # #     unit="faults",
        # #     value_type=int,
        # # )

        # # self._meter.create_observable_counter(
        # #     callback=self._get_system_swap_page_operations,
        # #     name="system.swap.page_operations",
        # #     description="System swap page operations",
        # #     unit="operations",
        # #     value_type=int,
        # # )
        self._meter.create_observable_counter(
            callback=self._get_system_disk_io,
            name="system.disk.io",
            description="System disk IO",
            unit="bytes",
        )

        self._meter.create_observable_counter(
            callback=self._get_system_disk_operations,
            name="system.disk.operations",
            description="System disk operations",
            unit="operations",
        )

        self._meter.create_observable_counter(
            callback=self._get_system_disk_time,
            name="system.disk.time",
            description="System disk time",
            unit="seconds",
        )

        # self.accumulator.register_valueobserver(
        #     callback=self._get_system_filesystem_usage,
        #     name="system.filesystem.usage",
        #     description="System filesystem usage",
        #     unit="bytes",
        #     value_type=int,
        # )

        # self._meter.create_observable_gauge(
        #     callback=self._get_system_filesystem_utilization,
        #     name="system.filesystem.utilization",
        #     description="System filesystem utilization",
        #     unit="1",
        #     value_type=float,
        # )

        self._meter.create_observable_counter(
            callback=self._get_system_network_dropped_packets,
            name="system.network.dropped_packets",
            description="System network dropped_packets",
            unit="packets",
        )

        self._meter.create_observable_counter(
            callback=self._get_system_network_packets,
            name="system.network.packets",
            description="System network packets",
            unit="packets",
        )

        self._meter.create_observable_counter(
            callback=self._get_system_network_errors,
            name="system.network.errors",
            description="System network errors",
            unit="errors",
        )

        self._meter.create_observable_counter(
            callback=self._get_system_network_io,
            name="system.network.io",
            description="System network io",
            unit="bytes",
        )

        self._meter.create_observable_up_down_counter(
            callback=self._get_system_network_connections,
            name="system.network.connections",
            description="System network connections",
            unit="connections",
        )

        self._meter.create_observable_counter(
            callback=self._get_runtime_memory,
            name="runtime.{}.memory".format(self._python_implementation),
            description="Runtime {} memory".format(
                self._python_implementation
            ),
            unit="bytes",
        )

        self._meter.create_observable_counter(
            callback=self._get_runtime_cpu_time,
            name="runtime.{}.cpu_time".format(self._python_implementation),
            description="Runtime {} CPU time".format(
                self._python_implementation
            ),
            unit="seconds",
        )

        self._meter.create_observable_counter(
            callback=self._get_runtime_gc_count,
            name="runtime.{}.gc_count".format(self._python_implementation),
            description="Runtime {} GC count".format(
                self._python_implementation
            ),
            unit="bytes",
        )

    def _uninstrument(self, **__):
        pass

    def _get_system_cpu_time(self) -> Iterable[Measurement]:
        """Observer callback for system CPU time

        Args:
            observer: the observer to update
        """
        for cpu, times in enumerate(psutil.cpu_times(percpu=True)):
            for metric in self._config["system.cpu.time"]:
                if hasattr(times, metric):
                    self._system_cpu_time_labels["state"] = metric
                    self._system_cpu_time_labels["cpu"] = cpu + 1
                    yield Measurement(
                        getattr(times, metric), self._system_cpu_time_labels
                    )

    def _get_system_cpu_utilization(self) -> Iterable[Measurement]:
        """Observer callback for system CPU utilization

        Args:
            observer: the observer to update
        """

        for cpu, times_percent in enumerate(
            psutil.cpu_times_percent(percpu=True)
        ):
            for metric in self._config["system.cpu.utilization"]:
                if hasattr(times_percent, metric):
                    self._system_cpu_utilization_labels["state"] = metric
                    self._system_cpu_utilization_labels["cpu"] = cpu + 1
                    yield Measurement(
                        getattr(times_percent, metric) / 100,
                        self._system_cpu_utilization_labels,
                    )

    def _get_system_memory_usage(self) -> Iterable[Measurement]:
        """Observer callback for memory usage

        Args:
            observer: the observer to update
        """
        virtual_memory = psutil.virtual_memory()
        for metric in self._config["system.memory.usage"]:
            self._system_memory_usage_labels["state"] = metric
            if hasattr(virtual_memory, metric):
                yield Measurement(
                    getattr(virtual_memory, metric),
                    self._system_memory_usage_labels,
                )

    def _get_system_memory_utilization(self) -> Iterable[Measurement]:
        """Observer callback for memory utilization

        Args:
            observer: the observer to update
        """
        system_memory = psutil.virtual_memory()

        for metric in self._config["system.memory.utilization"]:
            self._system_memory_utilization_labels["state"] = metric
            if hasattr(system_memory, metric):
                yield Measurement(
                    getattr(system_memory, metric) / system_memory.total,
                    self._system_memory_utilization_labels,
                )

    def _get_system_swap_usage(self) -> Iterable[Measurement]:
        """Observer callback for swap usage

        Args:
            observer: the observer to update
        """
        system_swap = psutil.swap_memory()

        for metric in self._config["system.swap.usage"]:
            self._system_swap_usage_labels["state"] = metric
            if hasattr(system_swap, metric):
                yield Measurement(
                    getattr(system_swap, metric),
                    self._system_swap_usage_labels,
                )

    def _get_system_swap_utilization(self) -> Iterable[Measurement]:
        """Observer callback for swap utilization

        Args:
            observer: the observer to update
        """
        system_swap = psutil.swap_memory()

        for metric in self._config["system.swap.utilization"]:
            if hasattr(system_swap, metric):
                self._system_swap_utilization_labels["state"] = metric
                yield Measurement(
                    getattr(system_swap, metric) / system_swap.total,
                    self._system_swap_utilization_labels,
                )

    # TODO Add _get_system_swap_page_faults
    # TODO Add _get_system_swap_page_operations

    def _get_system_disk_io(self) -> Iterable[Measurement]:
        """Observer callback for disk IO

        Args:
            observer: the observer to update
        """
        for device, counters in psutil.disk_io_counters(perdisk=True).items():
            for metric in self._config["system.disk.io"]:
                if hasattr(counters, "{}_bytes".format(metric)):
                    self._system_disk_io_labels["device"] = device
                    self._system_disk_io_labels["direction"] = metric
                    yield Measurement(
                        getattr(counters, "{}_bytes".format(metric)),
                        self._system_disk_io_labels,
                    )

    def _get_system_disk_operations(self) -> Iterable[Measurement]:
        """Observer callback for disk operations

        Args:
            observer: the observer to update
        """
        for device, counters in psutil.disk_io_counters(perdisk=True).items():
            for metric in self._config["system.disk.operations"]:
                if hasattr(counters, "{}_count".format(metric)):
                    self._system_disk_operations_labels["device"] = device
                    self._system_disk_operations_labels["direction"] = metric
                    yield Measurement(
                        getattr(counters, "{}_count".format(metric)),
                        self._system_disk_operations_labels,
                    )

    def _get_system_disk_time(self) -> Iterable[Measurement]:
        """Observer callback for disk time

        Args:
            observer: the observer to update
        """
        for device, counters in psutil.disk_io_counters(perdisk=True).items():
            for metric in self._config["system.disk.time"]:
                if hasattr(counters, "{}_time".format(metric)):
                    self._system_disk_time_labels["device"] = device
                    self._system_disk_time_labels["direction"] = metric
                    yield Measurement(
                        getattr(counters, "{}_time".format(metric)) / 1000,
                        self._system_disk_time_labels,
                    )

    def _get_system_disk_merged(self) -> Iterable[Measurement]:
        """Observer callback for disk merged operations

        Args:
            observer: the observer to update
        """

        # FIXME The units in the spec is 1, it seems like it should be
        # operations or the value type should be Double

        for device, counters in psutil.disk_io_counters(perdisk=True).items():
            for metric in self._config["system.disk.time"]:
                if hasattr(counters, "{}_merged_count".format(metric)):
                    self._system_disk_merged_labels["device"] = device
                    self._system_disk_merged_labels["direction"] = metric
                    yield Measurement(
                        getattr(counters, "{}_merged_count".format(metric)),
                        self._system_disk_merged_labels,
                    )

    # TODO Add _get_system_filesystem_usage
    # TODO Add _get_system_filesystem_utilization
    # TODO Filesystem information can be obtained with os.statvfs in Unix-like
    # OSs, how to do the same in Windows?

    def _get_system_network_dropped_packets(self) -> Iterable[Measurement]:
        """Observer callback for network dropped packets

        Args:
            observer: the observer to update
        """

        for device, counters in psutil.net_io_counters(pernic=True).items():
            for metric in self._config["system.network.dropped.packets"]:
                in_out = {"receive": "in", "transmit": "out"}[metric]
                if hasattr(counters, "drop{}".format(in_out)):
                    self._system_network_dropped_packets_labels[
                        "device"
                    ] = device
                    self._system_network_dropped_packets_labels[
                        "direction"
                    ] = metric
                    yield Measurement(
                        getattr(counters, "drop{}".format(in_out)),
                        self._system_network_dropped_packets_labels,
                    )

    def _get_system_network_packets(self) -> Iterable[Measurement]:
        """Observer callback for network packets

        Args:
            observer: the observer to update
        """

        for device, counters in psutil.net_io_counters(pernic=True).items():
            for metric in self._config["system.network.dropped.packets"]:
                recv_sent = {"receive": "recv", "transmit": "sent"}[metric]
                if hasattr(counters, "packets_{}".format(recv_sent)):
                    self._system_network_packets_labels["device"] = device
                    self._system_network_packets_labels["direction"] = metric
                    yield Measurement(
                        getattr(counters, "packets_{}".format(recv_sent)),
                        self._system_network_packets_labels,
                    )

    def _get_system_network_errors(self) -> Iterable[Measurement]:
        """Observer callback for network errors

        Args:
            observer: the observer to update
        """
        for device, counters in psutil.net_io_counters(pernic=True).items():
            for metric in self._config["system.network.errors"]:
                in_out = {"receive": "in", "transmit": "out"}[metric]
                if hasattr(counters, "err{}".format(in_out)):
                    self._system_network_errors_labels["device"] = device
                    self._system_network_errors_labels["direction"] = metric
                    yield Measurement(
                        getattr(counters, "err{}".format(in_out)),
                        self._system_network_errors_labels,
                    )

    def _get_system_network_io(self) -> Iterable[Measurement]:
        """Observer callback for network IO

        Args:
            observer: the observer to update
        """

        for device, counters in psutil.net_io_counters(pernic=True).items():
            for metric in self._config["system.network.dropped.packets"]:
                recv_sent = {"receive": "recv", "transmit": "sent"}[metric]
                if hasattr(counters, "bytes_{}".format(recv_sent)):
                    self._system_network_io_labels["device"] = device
                    self._system_network_io_labels["direction"] = metric
                    yield Measurement(
                        getattr(counters, "bytes_{}".format(recv_sent)),
                        self._system_network_io_labels,
                    )

    def _get_system_network_connections(self) -> Iterable[Measurement]:
        """Observer callback for network connections

        Args:
            observer: the observer to update
        """
        # TODO How to find the device identifier for a particular
        # connection?

        connection_counters = {}

        for net_connection in psutil.net_connections():
            for metric in self._config["system.network.connections"]:
                self._system_network_connections_labels["protocol"] = {
                    1: "tcp",
                    2: "udp",
                }[net_connection.type.value]
                self._system_network_connections_labels[
                    "state"
                ] = net_connection.status
                self._system_network_connections_labels[metric] = getattr(
                    net_connection, metric
                )

            connection_counters_key = get_dict_as_key(
                self._system_network_connections_labels
            )

            if connection_counters_key in connection_counters.keys():
                connection_counters[connection_counters_key]["counter"] += 1
            else:
                connection_counters[connection_counters_key] = {
                    "counter": 1,
                    "labels": self._system_network_connections_labels.copy(),
                }

        for connection_counter in connection_counters.values():
            yield Measurement(
                connection_counter["counter"],
                connection_counter["labels"],
            )

    def _get_runtime_memory(self) -> Iterable[Measurement]:
        """Observer callback for runtime memory

        Args:
            observer: the observer to update
        """
        proc_memory = self._proc.memory_info()
        for metric in self._config["runtime.memory"]:
            if hasattr(proc_memory, metric):
                self._runtime_memory_labels["type"] = metric
                yield Measurement(
                    getattr(proc_memory, metric),
                    self._runtime_memory_labels,
                )

    def _get_runtime_cpu_time(self) -> Iterable[Measurement]:
        """Observer callback for runtime CPU time

        Args:
            observer: the observer to update
        """
        proc_cpu = self._proc.cpu_times()
        for metric in self._config["runtime.cpu.time"]:
            if hasattr(proc_cpu, metric):
                self._runtime_cpu_time_labels["type"] = metric
                yield Measurement(
                    getattr(proc_cpu, metric),
                    self._runtime_cpu_time_labels,
                )

    def _get_runtime_gc_count(self) -> Iterable[Measurement]:
        """Observer callback for garbage collection

        Args:
            observer: the observer to update
        """
        for index, count in enumerate(gc.get_count()):
            self._runtime_gc_count_labels["count"] = str(index)
            yield Measurement(count, self._runtime_gc_count_labels)
