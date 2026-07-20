# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import subprocess
from types import SimpleNamespace
from unittest.mock import mock_open, patch

from opentelemetry.resource.detector.host import HostIdResourceDetector
from opentelemetry.sdk.resources import get_aggregated_resources
from opentelemetry.semconv._incubating.attributes.host_attributes import (
    HOST_ID,
)
from opentelemetry.test.test_base import TestBase
from opentelemetry.util._importlib_metadata import entry_points

MODULE = "opentelemetry.resource.detector.host"

_IOREG_OUTPUT = """+-o IOPlatformExpertDevice  <class IOPlatformExpertDevice>
    {
      "IOPlatformUUID" = "AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE"
      "IOPlatformSerialNumber" = "C02XXXXXXXXX"
    }
"""

_REG_OUTPUT = (
    "\r\nHKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Cryptography\r\n"
    "    MachineGuid    REG_SZ    12345678-90ab-cdef-1234-567890abcdef\r\n"
)


def _completed(stdout: str = "", returncode: int = 0) -> SimpleNamespace:
    return SimpleNamespace(stdout=stdout, stderr="", returncode=returncode)


class HostIdResourceDetectorTest(TestBase):
    def _assert_only_host_id(self, resource, expected: str) -> None:
        attributes = resource.attributes
        self.assertEqual(dict(attributes), {HOST_ID: expected})
        # Verify the value type matches the semconv spec (string).
        self.assertIsInstance(attributes[HOST_ID], str)

    # ---- Linux ----

    @patch(f"{MODULE}.platform.system", return_value="Linux")
    @patch(
        f"{MODULE}.open",
        new_callable=mock_open,
        read_data="linux-machine-id\n",
    )
    def test_linux_reads_etc_machine_id(self, mock_file, mock_system):
        self._assert_only_host_id(
            HostIdResourceDetector().detect(), "linux-machine-id"
        )

    @patch(f"{MODULE}.platform.system", return_value="Linux")
    @patch(
        f"{MODULE}._read_first_line",
        side_effect=[None, "dbus-machine-id"],
    )
    def test_linux_falls_back_to_dbus_machine_id(self, mock_read, mock_system):
        resource = HostIdResourceDetector().detect()
        self._assert_only_host_id(resource, "dbus-machine-id")
        self.assertEqual(
            [call.args[0] for call in mock_read.call_args_list],
            ["/etc/machine-id", "/var/lib/dbus/machine-id"],
        )

    @patch(f"{MODULE}.platform.system", return_value="Linux")
    @patch(f"{MODULE}._read_first_line", return_value=None)
    def test_linux_no_machine_id(self, mock_read, mock_system):
        resource = HostIdResourceDetector().detect()
        self.assertNotIn(HOST_ID, resource.attributes)

    # ---- macOS ----

    @patch(f"{MODULE}.platform.system", return_value="Darwin")
    @patch(f"{MODULE}.subprocess.run", return_value=_completed(_IOREG_OUTPUT))
    def test_macos_parses_ioreg_platform_uuid(self, mock_run, mock_system):
        self._assert_only_host_id(
            HostIdResourceDetector().detect(),
            "AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE",
        )

    @patch(f"{MODULE}.platform.system", return_value="Darwin")
    @patch(f"{MODULE}.subprocess.run", return_value=_completed("no uuid here"))
    def test_macos_no_platform_uuid(self, mock_run, mock_system):
        resource = HostIdResourceDetector().detect()
        self.assertNotIn(HOST_ID, resource.attributes)

    # ---- Windows ----

    @patch(f"{MODULE}.platform.system", return_value="Windows")
    @patch(f"{MODULE}.subprocess.run", return_value=_completed(_REG_OUTPUT))
    def test_windows_parses_machine_guid(self, mock_run, mock_system):
        self._assert_only_host_id(
            HostIdResourceDetector().detect(),
            "12345678-90ab-cdef-1234-567890abcdef",
        )

    @patch(f"{MODULE}.platform.system", return_value="Windows")
    @patch(
        f"{MODULE}.subprocess.run",
        return_value=_completed("", returncode=1),
    )
    def test_windows_registry_query_fails(self, mock_run, mock_system):
        resource = HostIdResourceDetector().detect()
        self.assertNotIn(HOST_ID, resource.attributes)

    @patch(f"{MODULE}.platform.system", return_value="Windows")
    @patch(
        f"{MODULE}.subprocess.run",
        return_value=_completed("no machine guid here"),
    )
    def test_windows_no_machine_guid(self, mock_run, mock_system):
        resource = HostIdResourceDetector().detect()
        self.assertNotIn(HOST_ID, resource.attributes)

    # ---- BSD ----

    @patch(f"{MODULE}.platform.system", return_value="FreeBSD")
    @patch(f"{MODULE}._read_first_line", return_value="bsd-host-id")
    def test_bsd_reads_etc_hostid(self, mock_read, mock_system):
        resource = HostIdResourceDetector().detect()
        self._assert_only_host_id(resource, "bsd-host-id")
        self.assertEqual(mock_read.call_args.args[0], "/etc/hostid")

    @patch(f"{MODULE}.platform.system", return_value="NetBSD")
    @patch(f"{MODULE}._read_first_line", return_value=None)
    @patch(
        f"{MODULE}.subprocess.run",
        return_value=_completed("bsd-kenv-uuid\n"),
    )
    def test_bsd_falls_back_to_kenv(self, mock_run, mock_read, mock_system):
        self._assert_only_host_id(
            HostIdResourceDetector().detect(), "bsd-kenv-uuid"
        )

    @patch(f"{MODULE}.platform.system", return_value="FreeBSD")
    @patch(f"{MODULE}._read_first_line", return_value=None)
    @patch(
        f"{MODULE}.subprocess.run",
        return_value=_completed("", returncode=1),
    )
    def test_bsd_no_host_id(self, mock_run, mock_read, mock_system):
        resource = HostIdResourceDetector().detect()
        self.assertNotIn(HOST_ID, resource.attributes)

    # ---- Unsupported / error paths ----

    @patch(f"{MODULE}.platform.system", return_value="Java")
    def test_unsupported_os_returns_empty(self, mock_system):
        resource = HostIdResourceDetector().detect()
        self.assertNotIn(HOST_ID, resource.attributes)

    @patch(f"{MODULE}.platform.system", return_value="Darwin")
    @patch(
        f"{MODULE}.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="ioreg", timeout=5),
    )
    def test_command_timeout_returns_empty(self, mock_run, mock_system):
        resource = HostIdResourceDetector().detect()
        self.assertNotIn(HOST_ID, resource.attributes)

    @patch(f"{MODULE}.platform.system", return_value="Darwin")
    @patch(f"{MODULE}.subprocess.run", side_effect=FileNotFoundError)
    def test_command_not_found_returns_empty(self, mock_run, mock_system):
        resource = HostIdResourceDetector().detect()
        self.assertNotIn(HOST_ID, resource.attributes)

    @patch(f"{MODULE}._get_host_id", side_effect=ValueError("boom"))
    def test_error_swallowed_by_default(self, mock_get):
        resource = HostIdResourceDetector().detect()
        self.assertNotIn(HOST_ID, resource.attributes)

    @patch(f"{MODULE}._get_host_id", side_effect=ValueError("boom"))
    def test_raise_on_error(self, mock_get):
        with self.assertRaises(ValueError):
            HostIdResourceDetector(raise_on_error=True).detect()

    # ---- Integration ----

    @patch(f"{MODULE}._get_host_id", return_value="agg-host-id")
    def test_host_id_via_aggregated_resources(self, mock_get):
        resource = get_aggregated_resources([HostIdResourceDetector()])
        self.assertEqual(resource.attributes[HOST_ID], "agg-host-id")

    def test_host_id_entrypoint(self):
        (entrypoint,) = entry_points(
            group="opentelemetry_resource_detector", name="host_id"
        )
        detector = entrypoint.load()()
        self.assertIsInstance(detector, HostIdResourceDetector)
