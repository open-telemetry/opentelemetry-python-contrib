# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import unittest
from collections.abc import Mapping
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from opentelemetry.resource.detector.azure._utils import _is_on_aks
from opentelemetry.resource.detector.azure.aks import (
    AzureAKSResourceDetector,
)
from opentelemetry.resource.detector.azure.vm import AzureVMResourceDetector
from opentelemetry.sdk.resources import (
    OTELResourceDetector,
    get_aggregated_resources,
)

TEST_RESOURCE_ID = (
    "/subscriptions/test-sub/resourceGroups/test-rg/providers/"
    "Microsoft.ContainerService/managedClusters/test-aks-cluster"
)
TEST_POD_NAME = "test-app-5f6c7d8b9f-abcde"
TEST_POD_UID = "627cc493-f310-47de-96bd-71410b7dec09"


class TestAzureAKSResourceDetector(unittest.TestCase):
    def test_is_process_dependent(self) -> None:
        detector = AzureAKSResourceDetector()

        self.assertTrue(detector.is_process_dependent())

    @patch.dict("os.environ", {"CLUSTER_RESOURCE_ID": TEST_RESOURCE_ID}, clear=True)
    def test_detects_aks_from_environment(self) -> None:
        attributes = AzureAKSResourceDetector().detect().attributes

        self.assertEqual(attributes["cloud.provider"], "azure")
        self.assertEqual(attributes["cloud.platform"], "azure.aks")
        self.assertEqual(attributes["cloud.resource_id"], TEST_RESOURCE_ID)
        self.assertEqual(attributes["cloud.account.id"], "test-sub")
        self.assertNotIn("k8s.cluster.name", attributes)
        self.assertNotIn("k8s.pod.name", attributes)
        self.assertNotIn("k8s.pod.uid", attributes)
        self.assertNotIn("service.instance.id", attributes)
        self.assertIsInstance(attributes["cloud.provider"], str)
        self.assertIsInstance(attributes["cloud.platform"], str)
        self.assertIsInstance(attributes["cloud.resource_id"], str)
        self.assertIsInstance(attributes["cloud.account.id"], str)

    def test_detects_optional_pod_identity(self) -> None:
        cases = (
            (
                {"K8S_POD_NAME": TEST_POD_NAME, "K8S_POD_UID": TEST_POD_UID},
                {"k8s.pod.name": TEST_POD_NAME, "k8s.pod.uid": TEST_POD_UID},
            ),
            ({"K8S_POD_NAME": TEST_POD_NAME}, {"k8s.pod.name": TEST_POD_NAME}),
            ({"K8S_POD_UID": TEST_POD_UID}, {"k8s.pod.uid": TEST_POD_UID}),
            (
                {"K8S_POD_NAME": TEST_POD_NAME, "K8S_POD_UID": ""},
                {"k8s.pod.name": TEST_POD_NAME},
            ),
            (
                {"K8S_POD_NAME": "", "K8S_POD_UID": TEST_POD_UID},
                {"k8s.pod.uid": TEST_POD_UID},
            ),
            ({"K8S_POD_NAME": "", "K8S_POD_UID": ""}, {}),
            ({"HOSTNAME": "custom-hostname"}, {}),
        )
        for pod_environment, expected_pod_attributes in cases:
            with (
                self.subTest(environment=pod_environment),
                patch.dict(
                    "os.environ",
                    {"CLUSTER_RESOURCE_ID": TEST_RESOURCE_ID, **pod_environment},
                    clear=True,
                ),
            ):
                attributes = AzureAKSResourceDetector().detect().attributes

                self.assertEqual(
                    attributes,
                    {
                        "cloud.provider": "azure",
                        "cloud.platform": "azure.aks",
                        "cloud.resource_id": TEST_RESOURCE_ID,
                        "cloud.account.id": "test-sub",
                        **expected_pod_attributes,
                    },
                )
                for key in expected_pod_attributes:
                    self.assertIsInstance(attributes[key], str)

    @patch.dict(
        "os.environ",
        {
            "CLUSTER_RESOURCE_ID": TEST_RESOURCE_ID,
            "K8S_POD_NAME": TEST_POD_NAME,
            "K8S_POD_UID": TEST_POD_UID,
        },
        clear=True,
    )
    def test_preserves_explicit_service_instance_ids_for_workers_sharing_a_pod(self) -> None:
        for instance_id in ("worker-1", "worker-2"):
            with (
                self.subTest(instance_id=instance_id),
                patch.dict(
                    "os.environ",
                    {"OTEL_RESOURCE_ATTRIBUTES": f"service.name=test-service,service.instance.id={instance_id}"},
                ),
            ):
                attributes = get_aggregated_resources([OTELResourceDetector(), AzureAKSResourceDetector()]).attributes

                self.assertEqual(attributes["service.name"], "test-service")
                self.assertEqual(attributes["service.instance.id"], instance_id)
                self.assertEqual(attributes["k8s.pod.name"], TEST_POD_NAME)
                self.assertEqual(attributes["k8s.pod.uid"], TEST_POD_UID)
                self.assertIsInstance(attributes["k8s.pod.name"], str)
                self.assertIsInstance(attributes["k8s.pod.uid"], str)

    @patch.dict(
        "os.environ",
        {
            "CLUSTER_RESOURCE_ID": (
                "/Subscriptions/test-sub/resourceGroups/test-rg/providers/"
                "Microsoft.ContainerService/ManagedClusters/my-cluster"
            )
        },
        clear=True,
    )
    def test_subscription_segment_is_case_insensitive(self) -> None:
        attributes = AzureAKSResourceDetector().detect().attributes

        self.assertEqual(attributes["cloud.account.id"], "test-sub")

    @patch.dict("os.environ", {"CLUSTER_RESOURCE_ID": "standalone-name"}, clear=True)
    def test_omits_account_id_without_subscription_segment(self) -> None:
        attributes = AzureAKSResourceDetector().detect().attributes

        self.assertNotIn("cloud.account.id", attributes)

    @patch.dict("os.environ", {}, clear=True)
    @patch(
        "opentelemetry.resource.detector.azure.aks._AKS_METADATA_FILE_PATH",
        "/missing/aks-cluster-metadata",
    )
    def test_returns_empty_resource_outside_aks(self) -> None:
        resource = AzureAKSResourceDetector().detect()

        self.assertEqual(resource.attributes, {})

    @patch.dict(
        "os.environ",
        {"K8S_POD_NAME": TEST_POD_NAME, "K8S_POD_UID": TEST_POD_UID},
        clear=True,
    )
    @patch(
        "opentelemetry.resource.detector.azure.aks._AKS_METADATA_FILE_PATH",
        "/missing/aks-cluster-metadata",
    )
    def test_pod_identity_alone_does_not_identify_aks(self) -> None:
        attributes = AzureAKSResourceDetector().detect().attributes

        self.assertEqual(attributes, {})

    @patch.dict(
        "os.environ",
        {"K8S_POD_NAME": TEST_POD_NAME, "K8S_POD_UID": TEST_POD_UID},
        clear=True,
    )
    def test_detects_aks_from_configmap_volume(self) -> None:
        with TemporaryDirectory() as directory:
            metadata_path = Path(directory) / "aks-cluster-metadata"
            metadata_path.mkdir()
            (metadata_path / "clusterResourceId").write_text(f"{TEST_RESOURCE_ID}\n", encoding="utf-8")

            with patch(
                "opentelemetry.resource.detector.azure.aks._AKS_METADATA_FILE_PATH",
                str(metadata_path),
            ):
                attributes = AzureAKSResourceDetector().detect().attributes

        self.assertEqual(attributes["cloud.resource_id"], TEST_RESOURCE_ID)
        self.assertEqual(attributes["k8s.pod.name"], TEST_POD_NAME)
        self.assertEqual(attributes["k8s.pod.uid"], TEST_POD_UID)
        self.assertIsInstance(attributes["k8s.pod.name"], str)
        self.assertIsInstance(attributes["k8s.pod.uid"], str)
        self.assertNotIn("service.instance.id", attributes)

    @patch.dict(
        "os.environ",
        {"K8S_POD_NAME": TEST_POD_NAME, "K8S_POD_UID": TEST_POD_UID},
        clear=True,
    )
    def test_detects_aks_from_subpath_mount(self) -> None:
        with TemporaryDirectory() as directory:
            metadata_path = Path(directory) / "aks-cluster-metadata"
            metadata_path.write_text(f"{TEST_RESOURCE_ID}\n", encoding="utf-8")

            with patch(
                "opentelemetry.resource.detector.azure.aks._AKS_METADATA_FILE_PATH",
                str(metadata_path),
            ):
                attributes = AzureAKSResourceDetector().detect().attributes

        self.assertEqual(attributes["cloud.resource_id"], TEST_RESOURCE_ID)
        self.assertEqual(attributes["k8s.pod.name"], TEST_POD_NAME)
        self.assertEqual(attributes["k8s.pod.uid"], TEST_POD_UID)
        self.assertIsInstance(attributes["k8s.pod.name"], str)
        self.assertIsInstance(attributes["k8s.pod.uid"], str)
        self.assertNotIn("service.instance.id", attributes)

    @patch.dict(
        "os.environ",
        {"K8S_POD_NAME": TEST_POD_NAME, "K8S_POD_UID": TEST_POD_UID},
        clear=True,
    )
    def test_detects_aks_from_key_value_file(self) -> None:
        content = f"\ufeff# AKS metadata\r\nclusterResourceId={TEST_RESOURCE_ID}\r\n"

        attributes = self._detect_from_file(content)

        self.assertEqual(attributes["cloud.resource_id"], TEST_RESOURCE_ID)
        self.assertEqual(attributes["k8s.pod.name"], TEST_POD_NAME)
        self.assertEqual(attributes["k8s.pod.uid"], TEST_POD_UID)
        self.assertIsInstance(attributes["k8s.pod.name"], str)
        self.assertIsInstance(attributes["k8s.pod.uid"], str)
        self.assertNotIn("service.instance.id", attributes)

    @patch.dict("os.environ", {}, clear=True)
    def test_explicit_key_wins_over_bare_lines(self) -> None:
        content = f"clusterResourceId={TEST_RESOURCE_ID}\nstray-token\n// not a supported comment\n"

        attributes = self._detect_from_file(content)

        self.assertEqual(attributes["cloud.resource_id"], TEST_RESOURCE_ID)

    @patch.dict(
        "os.environ",
        {"K8S_POD_NAME": TEST_POD_NAME, "K8S_POD_UID": TEST_POD_UID},
        clear=True,
    )
    def test_ignores_ambiguous_bare_values(self) -> None:
        attributes = self._detect_from_file(f"{TEST_RESOURCE_ID}\nstray-token\n")

        self.assertEqual(attributes, {})

    @patch.dict(
        "os.environ",
        {"K8S_POD_NAME": TEST_POD_NAME, "K8S_POD_UID": TEST_POD_UID},
        clear=True,
    )
    def test_ignores_configmap_volume_without_resource_id(self) -> None:
        with TemporaryDirectory() as directory:
            metadata_path = Path(directory) / "aks-cluster-metadata"
            metadata_path.mkdir()
            (metadata_path / "somethingElse").write_text("value\n", encoding="utf-8")

            with patch(
                "opentelemetry.resource.detector.azure.aks._AKS_METADATA_FILE_PATH",
                str(metadata_path),
            ):
                attributes = AzureAKSResourceDetector().detect().attributes

        self.assertEqual(attributes, {})

    @patch.dict(
        "os.environ",
        {
            "CLUSTER_RESOURCE_ID": (
                "/subscriptions/test-sub/resourceGroups/test-rg/providers/"
                "Microsoft.ContainerService/managedClusters/from-env"
            )
        },
        clear=True,
    )
    def test_environment_takes_precedence_over_file(self) -> None:
        attributes = self._detect_from_file(TEST_RESOURCE_ID)

        self.assertEqual(
            attributes["cloud.resource_id"],
            "/subscriptions/test-sub/resourceGroups/test-rg/providers/"
            "Microsoft.ContainerService/managedClusters/from-env",
        )

    @patch.dict("os.environ", {"CLUSTER_RESOURCE_ID": TEST_RESOURCE_ID}, clear=True)
    @patch("opentelemetry.resource.detector.azure.vm.urlopen")
    def test_vm_detection_is_skipped_on_aks(self, mock_urlopen) -> None:
        resource = AzureVMResourceDetector().detect()

        self.assertEqual(resource.attributes, {})
        mock_urlopen.assert_not_called()

    @patch.dict("os.environ", {}, clear=True)
    def test_mounted_metadata_marks_environment_as_aks(self) -> None:
        with TemporaryDirectory() as directory:
            metadata_path = Path(directory) / "aks-cluster-metadata"
            metadata_path.write_text(TEST_RESOURCE_ID, encoding="utf-8")

            with patch(
                "opentelemetry.resource.detector.azure._utils._AKS_METADATA_FILE_PATH",
                str(metadata_path),
            ):
                self.assertTrue(_is_on_aks())

    @staticmethod
    def _detect_from_file(content: str) -> Mapping[str, object]:
        with TemporaryDirectory() as directory:
            metadata_path = Path(directory) / "aks-cluster-metadata"
            metadata_path.write_text(content, encoding="utf-8")
            with patch(
                "opentelemetry.resource.detector.azure.aks._AKS_METADATA_FILE_PATH",
                str(metadata_path),
            ):
                return AzureAKSResourceDetector().detect().attributes
