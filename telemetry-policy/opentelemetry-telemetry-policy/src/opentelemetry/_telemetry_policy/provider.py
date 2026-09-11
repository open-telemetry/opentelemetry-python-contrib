# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import hashlib
import threading
from abc import ABC, abstractmethod
from logging import getLogger
from pathlib import Path

from opentelemetry._telemetry_policy.model import SourceKind
from opentelemetry._telemetry_policy.parser import parse_policy_document
from opentelemetry._telemetry_policy.store import PolicyStore

_logger = getLogger(__name__)


class PolicyProvider(ABC):
    """A source of policy snapshots feeding a :class:`PolicyStore`."""

    @property
    @abstractmethod
    def source_kind(self) -> SourceKind:
        """The source kind determining this provider's merge priority."""

    @abstractmethod
    def start(self) -> None:
        """Start supplying policies to the store."""

    @abstractmethod
    def shutdown(self, timeout: float | None = None) -> None:
        """Stop supplying policies. The last snapshot stays in effect."""


class FilePolicyProvider(PolicyProvider):
    """Reads a policy document from a local file, polling it for changes.

    Args:
        path: the policy document file.
        store: the store to push snapshots into.
        poll_interval: seconds between change checks. ``0`` reads the file
            once at :meth:`start` and never again.
    """

    def __init__(
        self,
        *,
        path: Path,
        store: PolicyStore,
        poll_interval: float = 30.0,
    ) -> None:
        self._path = path
        self._store = store
        self._poll_interval = poll_interval
        self._digest: bytes | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def source_kind(self) -> SourceKind:
        return SourceKind.FILE

    def start(self) -> None:
        self._load()
        if self._poll_interval > 0:
            self._thread = threading.Thread(
                target=self._poll,
                name="OtelTelemetryPolicyFileProvider",
                daemon=True,
            )
            self._thread.start()

    def shutdown(self, timeout: float | None = None) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
            self._thread = None

    def _poll(self) -> None:
        while not self._stop.wait(self._poll_interval):
            self._load()

    def _load(self) -> None:
        try:
            data = self._path.read_bytes()
        except OSError as exc:
            _logger.warning("cannot read policy file '%s', keeping previous policies: %s", self._path, exc)
            return
        digest = hashlib.sha256(data).digest()
        if digest == self._digest:
            return
        self._digest = digest
        try:
            result = parse_policy_document(data.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            _logger.warning("cannot parse policy file '%s', keeping previous policies: %s", self._path, exc)
            return
        for error in result.errors:
            _logger.warning("skipping invalid policy '%s' in '%s': %s", error.policy_id, self._path, error.message)
        statuses = self._store.set_policies(self.source_kind, result.policies)
        for status in statuses:
            if not status.applied:
                _logger.warning("policy '%s' from '%s' not applied: %s", status.policy_id, self._path, status.error)
