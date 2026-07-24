# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
import platform
import subprocess
import sys
from importlib.metadata import entry_points
from types import SimpleNamespace
from unittest import TestCase, skipUnless
from unittest.mock import MagicMock, patch

from opentelemetry.resource.detector.host import (
    HostIdResourceDetector,
    _windows_reg_path,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv._incubating.attributes.host_attributes import (
    HOST_ID,
)

MODULE = "opentelemetry.resource.detector.host"

_IOREG_OUTPUT = """+-o IOPlatformExpertDevice  <class IOPlatformExpertDevice>
    {
      "IOPlatformUUID" = "AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE"
      "IOPlatformSerialNumber" = "C02XXXXXXXXX"
    }
"""


def _completed(stdout: str = "", return_code: int = 0) -> SimpleNamespace:
    return SimpleNamespace(stdout=stdout, stderr="", returncode=return_code)


class HostIdResourceDetectorTest(TestCase):
    def _assert_only_host_id(self, resource: Resource, expected: str) -> None:
        attributes = resource.attributes
        self.assertEqual(dict(attributes), {HOST_ID: expected})
        self.assertIsInstance(attributes[HOST_ID], str)

    @skipUnless(
        platform.system() == "Linux",
        "Linux specific host.id end-to-end detection",
    )
    def test_linux_end_to_end(self) -> None:
        # Read the machine-id directly as an independent oracle for the exact
        # value the detector should return.
        expected = None
        for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            try:
                with open(path, encoding="utf8") as machine_id_file:
                    expected = machine_id_file.read().strip()
            except OSError:
                continue
            if expected:
                break

        resource = HostIdResourceDetector().detect()
        if expected:
            # A machine-id is a 32 character lowercase hexadecimal string.
            self.assertRegex(expected, r"^[0-9a-f]{32}$")
            self.assertEqual(resource.attributes[HOST_ID], expected)
        else:
            # No machine-id on this host, so the detector must report nothing.
            self.assertNotIn(HOST_ID, resource.attributes)

    @skipUnless(
        platform.system() == "Windows",
        "Windows specific host.id end-to-end detection",
    )
    def test_windows_end_to_end(self) -> None:
        # Guard on sys.platform (in addition to the skip decorator) so the
        # type checker only analyzes the Windows-only winreg usage on Windows.
        if sys.platform != "win32":
            return

        import winreg  # pylint: disable=import-outside-toplevel  # noqa: PLC0415

        # winreg reads the registry through the Win32 API, an independent
        # mechanism from the detector's reg.exe subprocess, so it is a valid
        # oracle for the exact value the detector should return.
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
        ) as key:
            machine_guid, _ = winreg.QueryValueEx(key, "MachineGuid")

        resource = HostIdResourceDetector().detect()
        self.assertIn(HOST_ID, resource.attributes)
        self.assertEqual(resource.attributes[HOST_ID], machine_guid)

    @patch(f"{MODULE}.platform.system", return_value="Linux")
    @patch(
        f"{MODULE}._read_first_line",
        side_effect=[None, "dbus-machine-id"],
    )
    def test_linux_falls_back_to_dbus_machine_id(
        self, mock_read: MagicMock, mock_system: MagicMock
    ) -> None:
        resource = HostIdResourceDetector().detect()
        self._assert_only_host_id(resource, "dbus-machine-id")
        self.assertEqual(
            [call.args[0] for call in mock_read.call_args_list],
            ["/etc/machine-id", "/var/lib/dbus/machine-id"],
        )

    @patch(f"{MODULE}.platform.system", return_value="Linux")
    @patch(f"{MODULE}._read_first_line", return_value=None)
    def test_linux_no_machine_id(
        self, mock_read: MagicMock, mock_system: MagicMock
    ) -> None:
        resource = HostIdResourceDetector().detect()
        self.assertNotIn(HOST_ID, resource.attributes)

    @patch(f"{MODULE}.platform.system", return_value="Darwin")
    @patch(f"{MODULE}.subprocess.run", return_value=_completed(_IOREG_OUTPUT))
    def test_macos_parses_ioreg_platform_uuid(
        self, mock_run: MagicMock, mock_system: MagicMock
    ) -> None:
        self._assert_only_host_id(
            HostIdResourceDetector().detect(),
            "AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE",
        )

    @patch(f"{MODULE}.platform.system", return_value="Darwin")
    @patch(f"{MODULE}.subprocess.run", return_value=_completed("no uuid here"))
    def test_macos_no_platform_uuid(
        self, mock_run: MagicMock, mock_system: MagicMock
    ) -> None:
        resource = HostIdResourceDetector().detect()
        self.assertNotIn(HOST_ID, resource.attributes)

    @patch(f"{MODULE}.platform.system", return_value="Windows")
    @patch(
        f"{MODULE}.subprocess.run",
        return_value=_completed("", return_code=1),
    )
    def test_windows_registry_query_fails(
        self, mock_run: MagicMock, mock_system: MagicMock
    ) -> None:
        resource = HostIdResourceDetector().detect()
        self.assertNotIn(HOST_ID, resource.attributes)

    @patch(f"{MODULE}.platform.system", return_value="Windows")
    @patch(
        f"{MODULE}.subprocess.run",
        return_value=_completed("no machine guid here"),
    )
    def test_windows_no_machine_guid(
        self, mock_run: MagicMock, mock_system: MagicMock
    ) -> None:
        resource = HostIdResourceDetector().detect()
        self.assertNotIn(HOST_ID, resource.attributes)

    def test_windows_reg_path_prefers_system_root(self) -> None:
        with patch.dict(
            "os.environ",
            {"SystemRoot": r"D:\WinDir", "WINDIR": r"E:\Other"},
            clear=True,
        ):
            self.assertEqual(
                _windows_reg_path(),
                os.path.join(r"D:\WinDir", "System32", "reg.exe"),
            )

    def test_windows_reg_path_falls_back_to_windir(self) -> None:
        with patch.dict("os.environ", {"WINDIR": r"E:\Other"}, clear=True):
            self.assertEqual(
                _windows_reg_path(),
                os.path.join(r"E:\Other", "System32", "reg.exe"),
            )

    def test_windows_reg_path_falls_back_to_default(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(
                _windows_reg_path(),
                os.path.join(r"C:\Windows", "System32", "reg.exe"),
            )

    @patch(f"{MODULE}.platform.system", return_value="FreeBSD")
    @patch(f"{MODULE}._read_first_line", return_value="bsd-host-id")
    def test_bsd_reads_etc_hostid(
        self, mock_read: MagicMock, mock_system: MagicMock
    ) -> None:
        resource = HostIdResourceDetector().detect()
        self._assert_only_host_id(resource, "bsd-host-id")
        self.assertEqual(mock_read.call_args.args[0], "/etc/hostid")

    @patch(f"{MODULE}.platform.system", return_value="NetBSD")
    @patch(f"{MODULE}._read_first_line", return_value=None)
    @patch(
        f"{MODULE}.subprocess.run",
        return_value=_completed("bsd-kenv-uuid\n"),
    )
    def test_bsd_falls_back_to_kenv(
        self,
        mock_run: MagicMock,
        mock_read: MagicMock,
        mock_system: MagicMock,
    ) -> None:
        self._assert_only_host_id(
            HostIdResourceDetector().detect(), "bsd-kenv-uuid"
        )

    @patch(f"{MODULE}.platform.system", return_value="FreeBSD")
    @patch(f"{MODULE}._read_first_line", return_value=None)
    @patch(
        f"{MODULE}.subprocess.run",
        return_value=_completed("", return_code=1),
    )
    def test_bsd_no_host_id(
        self,
        mock_run: MagicMock,
        mock_read: MagicMock,
        mock_system: MagicMock,
    ) -> None:
        resource = HostIdResourceDetector().detect()
        self.assertNotIn(HOST_ID, resource.attributes)

    @patch(f"{MODULE}.platform.system", return_value="Java")
    def test_unsupported_os_returns_empty(
        self, mock_system: MagicMock
    ) -> None:
        resource = HostIdResourceDetector().detect()
        self.assertNotIn(HOST_ID, resource.attributes)

    # Failure modes of the subprocess-backed lookups must not raise.

    @patch(f"{MODULE}.platform.system", return_value="Darwin")
    @patch(
        f"{MODULE}.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="ioreg", timeout=5),
    )
    def test_command_timeout_returns_empty(
        self, mock_run: MagicMock, mock_system: MagicMock
    ) -> None:
        resource = HostIdResourceDetector().detect()
        self.assertNotIn(HOST_ID, resource.attributes)

    @patch(f"{MODULE}.platform.system", return_value="Darwin")
    @patch(f"{MODULE}.subprocess.run", side_effect=FileNotFoundError)
    def test_command_not_found_returns_empty(
        self, mock_run: MagicMock, mock_system: MagicMock
    ) -> None:
        resource = HostIdResourceDetector().detect()
        self.assertNotIn(HOST_ID, resource.attributes)

    @patch(f"{MODULE}._get_host_id", side_effect=ValueError("boom"))
    def test_error_swallowed_by_default(self, mock_get: MagicMock) -> None:
        resource = HostIdResourceDetector().detect()
        self.assertNotIn(HOST_ID, resource.attributes)

    @patch(f"{MODULE}._get_host_id", side_effect=ValueError("boom"))
    def test_raise_on_error(self, mock_get: MagicMock) -> None:
        with self.assertRaises(ValueError):
            HostIdResourceDetector(raise_on_error=True).detect()

    def test_host_id_entrypoint(self) -> None:
        (entrypoint,) = entry_points(
            group="opentelemetry_resource_detector", name="host_id"
        )
        detector = entrypoint.load()()
        self.assertIsInstance(detector, HostIdResourceDetector)
