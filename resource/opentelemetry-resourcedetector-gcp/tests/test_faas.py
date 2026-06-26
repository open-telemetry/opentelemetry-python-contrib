# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from unittest.mock import MagicMock

import pytest
from opentelemetry.resource.detector.gcp import _faas


# Reset stuff before every test
# pylint: disable=unused-argument
@pytest.fixture(autouse=True)
def autouse(fake_get_metadata):
    pass


def test_detects_on_cloud_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("K_CONFIGURATION", "fake-configuration")
    assert _faas.on_cloud_run()


def test_detects_not_on_cloud_run() -> None:
    assert not _faas.on_cloud_run()


def test_detects_on_cloud_functions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FUNCTION_TARGET", "fake-function-target")
    assert _faas.on_cloud_functions()


def test_detects_not_on_cloud_functions() -> None:
    assert not _faas.on_cloud_functions()


def test_detects_faas_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("K_SERVICE", "fake-service")
    assert _faas.faas_name() == "fake-service"


def test_detects_faas_version(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("K_REVISION", "fake-revision")
    assert _faas.faas_version() == "fake-revision"


def test_detects_faas_instance(fake_get_metadata: MagicMock) -> None:
    fake_get_metadata.return_value = {"instance": {"id": "0087244a"}}
    assert _faas.faas_instance() == "0087244a"


def test_detects_faas_region(fake_get_metadata: MagicMock) -> None:
    fake_get_metadata.return_value = {
        "instance": {"region": "projects/233510669999/regions/us-east4"}
    }
    assert _faas.faas_cloud_region() == "us-east4"
