# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import MagicMock

import pytest

from opentelemetry.resource.detector.gcp import _metadata


@pytest.fixture(name="fake_get_metadata")
def fixture_fake_get_metadata(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock = MagicMock()
    monkeypatch.setattr(_metadata, "get_metadata", mock)
    return mock
