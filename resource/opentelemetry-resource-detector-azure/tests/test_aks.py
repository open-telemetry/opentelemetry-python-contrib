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

TEST_RESOURCE_ID = (
    "/subscriptions/test-sub/resourceGroups/test-rg/providers/"
    "Microsoft.ContainerService/managedClusters/test-aks-cluster"
)


class TestAzureAKSResourceDetector(unittest.TestCase):
    @patch.dict("os.environ", {"CLUSTER_RESOURCE_ID": TEST_RESOURCE_ID}, clear=True)
    def test_detects_aks_from_environment(self) -> None:
        attributes = AzureAKSResourceDetector().detect().attributes

        self.assertEqual(attributes["cloud.provider"], "azure")
        self.assertEqual(attributes["cloud.platform"], "azure_aks")
        self.assertEqual(attributes["cloud.resource_id"], TEST_RESOURCE_ID)
        self.assertNotIn("k8s.cluster.name", attributes)
        self.assertIsInstance(attributes["cloud.provider"], str)
        self.assertIsInstance(attributes["cloud.platform"], str)
        self.assertIsInstance(attributes["cloud.resource_id"], str)

    @patch.dict("os.environ", {}, clear=True)
    @patch(
        "opentelemetry.resource.detector.azure.aks._AKS_METADATA_FILE_PATH",
        "/missing/aks-cluster-metadata",
    )
    def test_returns_empty_resource_outside_aks(self) -> None:
        resource = AzureAKSResourceDetector().detect()

        self.assertEqual(resource.attributes, {})

    @patch.dict("os.environ", {}, clear=True)
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

    @patch.dict("os.environ", {}, clear=True)
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

    @patch.dict("os.environ", {}, clear=True)
    def test_detects_aks_from_key_value_file(self) -> None:
        content = f"\ufeff# AKS metadata\r\nclusterResourceId={TEST_RESOURCE_ID}\r\n"

        attributes = self._detect_from_file(content)

        self.assertEqual(attributes["cloud.resource_id"], TEST_RESOURCE_ID)

    @patch.dict("os.environ", {}, clear=True)
    def test_explicit_key_wins_over_bare_lines(self) -> None:
        content = f"clusterResourceId={TEST_RESOURCE_ID}\nstray-token\n// not a supported comment\n"

        attributes = self._detect_from_file(content)

        self.assertEqual(attributes["cloud.resource_id"], TEST_RESOURCE_ID)

    @patch.dict("os.environ", {}, clear=True)
    def test_ignores_ambiguous_bare_values(self) -> None:
        attributes = self._detect_from_file(f"{TEST_RESOURCE_ID}\nstray-token\n")

        self.assertEqual(attributes, {})

    @patch.dict("os.environ", {}, clear=True)
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
