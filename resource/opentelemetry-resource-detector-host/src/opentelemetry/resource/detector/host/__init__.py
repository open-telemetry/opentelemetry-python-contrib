# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
import platform
import subprocess
from logging import getLogger

from opentelemetry.sdk.resources import Resource, ResourceDetector
from opentelemetry.semconv._incubating.attributes.host_attributes import (
    HOST_ID,
)

logger = getLogger(__name__)

# Non-privileged machine-id sources per the semantic conventions:
# https://opentelemetry.io/docs/specs/semconv/resource/host/#non-privileged-machine-id-lookup
_LINUX_MACHINE_ID_PATHS = ("/etc/machine-id", "/var/lib/dbus/machine-id")
_BSD_HOSTID_PATH = "/etc/hostid"
_BSD_KENV_COMMAND = ("/bin/kenv", "-q", "smbios.system.uuid")
_MACOS_IOREG_COMMAND = (
    "/usr/sbin/ioreg",
    "-rd1",
    "-c",
    "IOPlatformExpertDevice",
)
# Prefer the SystemRoot/WINDIR environment variables to locate the Windows
# directory, falling back to the conventional install path only if neither is
# set. SystemRoot and WINDIR normally point to the same directory.
_WINDOWS_ROOT_ENV_VARS = ("SystemRoot", "WINDIR")
_WINDOWS_ROOT_FALLBACK = r"C:\Windows"
_WINDOWS_REGISTRY_QUERY_ARGS = (
    "query",
    r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Cryptography",
    "/v",
    "MachineGuid",
)
_COMMAND_TIMEOUT_SECONDS = 5


def _windows_reg_path() -> str:
    for env_var in _WINDOWS_ROOT_ENV_VARS:
        root = os.environ.get(env_var)
        if root:
            break
    else:
        root = _WINDOWS_ROOT_FALLBACK
    return os.path.join(root, "System32", "reg.exe")


def _read_first_line(path: str) -> str | None:
    try:
        with open(path, encoding="utf8") as machine_id_file:
            for raw_line in machine_id_file:
                line = raw_line.strip()
                if line:
                    return line
    except OSError as exception:
        logger.debug("Failed to read %s: %s", path, exception)
    return None


def _run_command(command: tuple[str, ...]) -> str | None:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=_COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exception:
        logger.warning("Failed to run %s: %s", command[0], exception)
        return None
    if completed.returncode != 0:
        logger.warning(
            "Command %s exited with code %s", command[0], completed.returncode
        )
        return None
    return completed.stdout


def _get_linux_machine_id() -> str | None:
    for path in _LINUX_MACHINE_ID_PATHS:
        machine_id = _read_first_line(path)
        if machine_id:
            return machine_id
    return None


def _get_bsd_machine_id() -> str | None:
    machine_id = _read_first_line(_BSD_HOSTID_PATH)
    if machine_id:
        return machine_id
    output = _run_command(_BSD_KENV_COMMAND)
    if output:
        machine_id = output.strip()
        if machine_id:
            return machine_id
    return None


def _get_macos_machine_id() -> str | None:
    output = _run_command(_MACOS_IOREG_COMMAND)
    if not output:
        return None
    for line in output.splitlines():
        if "IOPlatformUUID" in line:
            # Line looks like: `    "IOPlatformUUID" = "AAAAAAAA-BBBB-..."`
            _, _, value = line.partition("=")
            machine_id = value.strip().strip('"').strip()
            if machine_id:
                return machine_id
    return None


def _get_windows_machine_id() -> str | None:
    command = (_windows_reg_path(), *_WINDOWS_REGISTRY_QUERY_ARGS)
    output = _run_command(command)
    if not output:
        return None
    for line in output.splitlines():
        if "MachineGuid" in line:
            # Line looks like: `    MachineGuid    REG_SZ    <value>`
            parts = line.split()
            if len(parts) == 3:
                return parts[2]
    return None


def _get_host_id() -> str | None:
    system = platform.system()
    match system:
        case "Linux":
            return _get_linux_machine_id()
        case "Darwin":
            return _get_macos_machine_id()
        case "Windows":
            return _get_windows_machine_id()
        case _ if system == "DragonFly" or system.endswith("BSD"):
            return _get_bsd_machine_id()
        case _:
            logger.warning(
                "Unsupported OS type for host.id detection: %s", system
            )
            return None


class HostIdResourceDetector(ResourceDetector):
    """Detects the ``host.id`` resource attribute from the non-privileged
    machine id of the host and returns it in a Resource
    """

    def detect(self) -> Resource:
        try:
            if host_id := _get_host_id():
                return Resource({HOST_ID: host_id})

        # pylint: disable=broad-except
        except Exception as exception:
            logger.warning(
                "%s Resource Detection failed silently: %s",
                self.__class__.__name__,
                exception,
            )
            if self.raise_on_error:
                raise exception
        return Resource.get_empty()
