# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import pytest

from opentelemetry._telemetry_policy import (
    FilePolicyProvider,
    PolicyStore,
    SourceKind,
    TraceSamplingPolicyImplementer,
    TraceTarget,
)


def _policy_document(percentage: float) -> str:
    return json.dumps(
        {
            "policies": [
                {
                    "id": "sample-database-spans",
                    "name": "Sample database spans",
                    "trace": {
                        "match": [{"span_attribute": ["db.system"], "exists": True}],
                        "keep": {"percentage": percentage},
                    },
                }
            ]
        }
    )


def _wait_until(condition: Any, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.01)
    raise AssertionError("condition not met within timeout")


def _current_percentages(store: PolicyStore) -> list[float]:
    # pylint: disable=protected-access
    return [
        policy.target.keep.percentage
        for policy in store._effective_policies()
        if isinstance(policy.target, TraceTarget)
    ]


def test_initial_load_applies_policies(tmp_path: Path) -> None:
    path = tmp_path / "policies.json"
    path.write_text(_policy_document(0.0))
    store = PolicyStore()
    store.add_implementer(TraceSamplingPolicyImplementer())
    provider = FilePolicyProvider(path=path, store=store, poll_interval=0)

    assert provider.source_kind is SourceKind.FILE
    provider.start()
    provider.shutdown()

    assert _current_percentages(store) == [0.0]


def test_poll_picks_up_changes(tmp_path: Path) -> None:
    path = tmp_path / "policies.json"
    path.write_text(_policy_document(0.0))
    store = PolicyStore()
    provider = FilePolicyProvider(path=path, store=store, poll_interval=0.05)

    provider.start()
    try:
        assert _current_percentages(store) == [0.0]
        path.write_text(_policy_document(100.0))
        _wait_until(lambda: _current_percentages(store) == [100.0])
    finally:
        provider.shutdown(timeout=5.0)


def test_unparseable_file_keeps_previous_policies(tmp_path: Path) -> None:
    path = tmp_path / "policies.json"
    path.write_text(_policy_document(0.0))
    store = PolicyStore()
    provider = FilePolicyProvider(path=path, store=store, poll_interval=0)
    provider.start()
    assert _current_percentages(store) == [0.0]

    path.write_text("{ not json")
    provider._load()  # pylint: disable=protected-access
    assert _current_percentages(store) == [0.0]

    path.unlink()
    provider._load()  # pylint: disable=protected-access
    assert _current_percentages(store) == [0.0]


def test_unchanged_invalid_file_not_reparsed_and_recovery_applies(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "policies.json"
    path.write_text(_policy_document(0.0))
    store = PolicyStore()
    provider = FilePolicyProvider(path=path, store=store, poll_interval=0)
    provider.start()

    path.write_text("{ not json")
    with caplog.at_level(logging.WARNING):
        provider._load()  # pylint: disable=protected-access
        provider._load()  # pylint: disable=protected-access
    parse_warnings = [record for record in caplog.records if "cannot parse" in record.getMessage()]
    assert len(parse_warnings) == 1
    assert _current_percentages(store) == [0.0]

    path.write_text(_policy_document(100.0))
    provider._load()  # pylint: disable=protected-access
    assert _current_percentages(store) == [100.0]


def test_empty_document_clears_policies(tmp_path: Path) -> None:
    path = tmp_path / "policies.json"
    path.write_text(_policy_document(0.0))
    store = PolicyStore()
    provider = FilePolicyProvider(path=path, store=store, poll_interval=0)
    provider.start()
    assert _current_percentages(store) == [0.0]

    path.write_text(json.dumps({"policies": []}))
    provider._load()  # pylint: disable=protected-access
    assert _current_percentages(store) == []
