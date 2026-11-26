# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import MagicMock

import pytest

from opentelemetry.resourcedetector.gcp_resource_detector import _faas


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


def test_detects_on_cloud_run_job(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLOUD_RUN_JOB", "fake-job")
    assert _faas.on_cloud_run_job()


def test_detects_not_on_cloud_run_job() -> None:
    assert not _faas.on_cloud_run_job()


def test_detects_on_cloud_run_worker_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLOUD_RUN_WORKER_POOL", "fake-worker-pool")
    assert _faas.on_cloud_run_worker_pool()


def test_detects_not_on_cloud_run_worker_pool() -> None:
    assert not _faas.on_cloud_run_worker_pool()


def test_detects_on_cloud_run_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLOUD_RUN_INSTANCE", "fake-instance")
    assert _faas.on_cloud_run_instance()


def test_detects_not_on_cloud_run_instance() -> None:
    assert not _faas.on_cloud_run_instance()


def test_detects_faas_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("K_SERVICE", "fake-service")
    assert _faas.faas_name() == "fake-service"


def test_detects_cloud_run_job_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLOUD_RUN_JOB", "fake-job")
    assert _faas.cloud_run_job_name() == "fake-job"


def test_detects_cloud_run_job_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _faas.cloud_run_job_execution() is None
    monkeypatch.setenv("CLOUD_RUN_EXECUTION", "fake-execution")
    assert _faas.cloud_run_job_execution() == "fake-execution"


def test_detects_cloud_run_job_task_index(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _faas.cloud_run_job_task_index() is None
    monkeypatch.setenv("CLOUD_RUN_TASK_INDEX", "2")
    assert _faas.cloud_run_job_task_index() == 2


def test_cloud_run_job_task_index_malformed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLOUD_RUN_TASK_INDEX", "not-an-int")
    assert _faas.cloud_run_job_task_index() is None


def test_detects_cloud_run_worker_pool_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLOUD_RUN_WORKER_POOL", "fake-worker-pool")
    assert _faas.cloud_run_worker_pool_name() == "fake-worker-pool"


def test_detects_cloud_run_worker_pool_revision(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _faas.cloud_run_worker_pool_revision() is None
    monkeypatch.setenv("CLOUD_RUN_REVISION", "fake-worker-pool-00001")
    assert _faas.cloud_run_worker_pool_revision() == "fake-worker-pool-00001"


def test_detects_cloud_run_instance_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLOUD_RUN_INSTANCE", "fake-instance")
    assert _faas.cloud_run_instance_name() == "fake-instance"


def test_detects_faas_version(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("K_REVISION", "fake-revision")
    assert _faas.faas_version() == "fake-revision"


def test_detects_faas_instance(fake_get_metadata: MagicMock) -> None:
    fake_get_metadata.return_value = {"instance": {"id": "0087244a"}}
    assert _faas.faas_instance() == "0087244a"


def test_detects_faas_region(fake_get_metadata: MagicMock) -> None:
    fake_get_metadata.return_value = {"instance": {"region": "projects/233510669999/regions/us-east4"}}
    assert _faas.faas_cloud_region() == "us-east4"
