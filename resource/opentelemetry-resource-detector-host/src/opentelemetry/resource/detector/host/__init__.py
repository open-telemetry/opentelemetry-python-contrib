# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

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
_BSD_KENV_COMMAND = ("kenv", "-q", "smbios.system.uuid")
_MACOS_IOREG_COMMAND = ("ioreg", "-rd1", "-c", "IOPlatformExpertDevice")
_WINDOWS_REGISTRY_COMMAND = (
    "reg",
    "query",
    r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Cryptography",
    "/v",
    "MachineGuid",
)
_COMMAND_TIMEOUT_SECONDS = 5


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
        logger.debug("Failed to run %s: %s", command[0], exception)
        return None
    if completed.returncode != 0:
        logger.debug(
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
    output = _run_command(_WINDOWS_REGISTRY_COMMAND)
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
    if system == "Linux":
        return _get_linux_machine_id()
    if system == "Darwin":
        return _get_macos_machine_id()
    if system == "Windows":
        return _get_windows_machine_id()
    if system == "DragonFly" or system.endswith("BSD"):
        return _get_bsd_machine_id()
    logger.debug("Unsupported OS type for host.id detection: %s", system)
    return None


class HostIdResourceDetector(ResourceDetector):
    """Detects the ``host.id`` resource attribute from the non-privileged
    machine id of the host and returns it in a Resource
    """

    def detect(self) -> Resource:
        try:
            host_id = _get_host_id()
            resource = Resource.get_empty()
            if host_id:
                resource = resource.merge(Resource({HOST_ID: host_id}))
            return resource

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
