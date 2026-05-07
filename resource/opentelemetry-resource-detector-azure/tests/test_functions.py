# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
import unittest
from unittest.mock import patch

# pylint: disable=no-name-in-module
from opentelemetry.resource.detector.azure.functions import (
    AzureFunctionsResourceDetector,
)

TEST_WEBSITE_SITE_NAME = "TEST_WEBSITE_SITE_NAME"
TEST_REGION_NAME = "TEST_REGION_NAME"
TEST_WEBSITE_INSTANCE_ID = "TEST_WEBSITE_INSTANCE_ID"

TEST_WEBSITE_RESOURCE_GROUP = "TEST_WEBSITE_RESOURCE_GROUP"
TEST_WEBSITE_OWNER_NAME = "TEST_WEBSITE_OWNER_NAME"
TEST_WEBSITE_MEMORY_LIMIT_MB = "1024"


class TestAzureAppServiceResourceDetector(unittest.TestCase):
    @patch.dict(
        "os.environ",
        {
            "FUNCTIONS_WORKER_RUNTIME": "1",
            "WEBSITE_SITE_NAME": TEST_WEBSITE_SITE_NAME,
            "REGION_NAME": TEST_REGION_NAME,
            "WEBSITE_INSTANCE_ID": TEST_WEBSITE_INSTANCE_ID,
            "WEBSITE_RESOURCE_GROUP": TEST_WEBSITE_RESOURCE_GROUP,
            "WEBSITE_OWNER_NAME": TEST_WEBSITE_OWNER_NAME,
            "WEBSITE_MEMORY_LIMIT_MB": TEST_WEBSITE_MEMORY_LIMIT_MB,
        },
        clear=True,
    )
    @patch("opentelemetry.resource.detector.azure.functions.getpid")
    def test_on_functions(self, pid_mock):
        pid_mock.return_value = 1000
        resource = AzureFunctionsResourceDetector().detect()
        attributes = resource.attributes
        self.assertEqual(attributes["service.name"], TEST_WEBSITE_SITE_NAME)
        self.assertEqual(attributes["cloud.provider"], "azure")
        self.assertEqual(attributes["cloud.platform"], "azure_functions")
        self.assertEqual(attributes["process.pid"], 1000)

        self.assertEqual(
            attributes["cloud.resource_id"],
            f"/subscriptions/{TEST_WEBSITE_OWNER_NAME}/resourceGroups/{TEST_WEBSITE_RESOURCE_GROUP}/providers/Microsoft.Web/sites/{TEST_WEBSITE_SITE_NAME}",
        )

        self.assertEqual(attributes["cloud.region"], TEST_REGION_NAME)
        self.assertEqual(attributes["faas.instance"], TEST_WEBSITE_INSTANCE_ID)
        self.assertEqual(attributes["faas.max_memory"], 1024)

    @patch.dict(
        "os.environ",
        {
            "FUNCTIONS_WORKER_RUNTIME": "1",
            "WEBSITE_SITE_NAME": TEST_WEBSITE_SITE_NAME,
            "REGION_NAME": TEST_REGION_NAME,
            "WEBSITE_INSTANCE_ID": TEST_WEBSITE_INSTANCE_ID,
            "WEBSITE_RESOURCE_GROUP": TEST_WEBSITE_RESOURCE_GROUP,
            "WEBSITE_OWNER_NAME": TEST_WEBSITE_OWNER_NAME,
            "WEBSITE_MEMORY_LIMIT_MB": "error",
        },
        clear=True,
    )
    @patch("opentelemetry.resource.detector.azure.functions.getpid")
    def test_on_functions_error_memory(self, pid_mock):
        pid_mock.return_value = 1000
        resource = AzureFunctionsResourceDetector().detect()
        attributes = resource.attributes
        self.assertEqual(attributes["service.name"], TEST_WEBSITE_SITE_NAME)
        self.assertEqual(attributes["cloud.provider"], "azure")
        self.assertEqual(attributes["cloud.platform"], "azure_functions")
        self.assertEqual(attributes["process.pid"], 1000)

        self.assertEqual(
            attributes["cloud.resource_id"],
            f"/subscriptions/{TEST_WEBSITE_OWNER_NAME}/resourceGroups/{TEST_WEBSITE_RESOURCE_GROUP}/providers/Microsoft.Web/sites/{TEST_WEBSITE_SITE_NAME}",
        )

        self.assertEqual(attributes["cloud.region"], TEST_REGION_NAME)
        self.assertEqual(attributes["faas.instance"], TEST_WEBSITE_INSTANCE_ID)
        self.assertIsNone(attributes.get("faas.max_memory"))

    @patch.dict(
        "os.environ",
        {
            "WEBSITE_SITE_NAME": TEST_WEBSITE_SITE_NAME,
            "REGION_NAME": TEST_REGION_NAME,
            "WEBSITE_INSTANCE_ID": TEST_WEBSITE_INSTANCE_ID,
            "WEBSITE_RESOURCE_GROUP": TEST_WEBSITE_RESOURCE_GROUP,
            "WEBSITE_OWNER_NAME": TEST_WEBSITE_OWNER_NAME,
            "WEBSITE_MEMORY_LIMIT_MB": TEST_WEBSITE_MEMORY_LIMIT_MB,
        },
        clear=True,
    )
    def test_off_app_service(self):
        resource = AzureFunctionsResourceDetector().detect()
        self.assertEqual(resource.attributes, {})
