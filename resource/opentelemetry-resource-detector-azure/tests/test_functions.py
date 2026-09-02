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

TEST_WEBSITE_RESOURCE_GROUP = "example-resource-group"
TEST_SUBSCRIPTION_ID = "00000000-0000-0000-0000-000000000000"
TEST_WEBSITE_OWNER_NAME = f"{TEST_SUBSCRIPTION_ID}+{TEST_WEBSITE_RESOURCE_GROUP}-WestEuropewebspace"
TEST_WEBSITE_MEMORY_LIMIT_MB = "1024"

TEST_FUNCTIONS_ENVIRONMENT = {
    "FUNCTIONS_WORKER_RUNTIME": "1",
    "WEBSITE_SITE_NAME": TEST_WEBSITE_SITE_NAME,
    "REGION_NAME": TEST_REGION_NAME,
    "WEBSITE_INSTANCE_ID": TEST_WEBSITE_INSTANCE_ID,
    "WEBSITE_RESOURCE_GROUP": TEST_WEBSITE_RESOURCE_GROUP,
    "WEBSITE_OWNER_NAME": TEST_WEBSITE_OWNER_NAME,
    "WEBSITE_MEMORY_LIMIT_MB": TEST_WEBSITE_MEMORY_LIMIT_MB,
}


class TestAzureAppServiceResourceDetector(unittest.TestCase):
    @patch.dict("os.environ", TEST_FUNCTIONS_ENVIRONMENT, clear=True)
    @patch("opentelemetry.resource.detector.azure.functions.getpid")
    def test_on_functions(self, pid_mock):
        pid_mock.return_value = 1000
        resource = AzureFunctionsResourceDetector().detect()
        attributes = resource.attributes
        self.assertEqual(attributes["service.name"], TEST_WEBSITE_SITE_NAME)
        self.assertEqual(attributes["cloud.provider"], "azure")
        self.assertEqual(attributes["cloud.platform"], "azure_functions")
        self.assertEqual(attributes["process.pid"], 1000)
        self.assertEqual(attributes["cloud.account.id"], TEST_SUBSCRIPTION_ID)
        self.assertIsInstance(attributes["cloud.account.id"], str)
        self.assertEqual(attributes["azure.resource_group.name"], TEST_WEBSITE_RESOURCE_GROUP)
        self.assertIsInstance(attributes["azure.resource_group.name"], str)

        self.assertEqual(
            attributes["cloud.resource_id"],
            f"/subscriptions/{TEST_SUBSCRIPTION_ID}/resourceGroups/{TEST_WEBSITE_RESOURCE_GROUP}/providers/Microsoft.Web/sites/{TEST_WEBSITE_SITE_NAME}",
        )

        self.assertEqual(attributes["cloud.region"], TEST_REGION_NAME)
        self.assertEqual(attributes["faas.instance"], TEST_WEBSITE_INSTANCE_ID)
        self.assertEqual(attributes["faas.max_memory"], 1024)

    @patch.dict(
        "os.environ",
        {**TEST_FUNCTIONS_ENVIRONMENT, "WEBSITE_MEMORY_LIMIT_MB": "error"},
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
        self.assertEqual(attributes["cloud.account.id"], TEST_SUBSCRIPTION_ID)
        self.assertEqual(attributes["azure.resource_group.name"], TEST_WEBSITE_RESOURCE_GROUP)

        self.assertEqual(
            attributes["cloud.resource_id"],
            f"/subscriptions/{TEST_SUBSCRIPTION_ID}/resourceGroups/{TEST_WEBSITE_RESOURCE_GROUP}/providers/Microsoft.Web/sites/{TEST_WEBSITE_SITE_NAME}",
        )

        self.assertEqual(attributes["cloud.region"], TEST_REGION_NAME)
        self.assertEqual(attributes["faas.instance"], TEST_WEBSITE_INSTANCE_ID)
        self.assertIsNone(attributes.get("faas.max_memory"))

    def test_missing_identity_environment_variables(self) -> None:
        expected_attributes = {
            "WEBSITE_OWNER_NAME": {
                "service.name": TEST_WEBSITE_SITE_NAME,
                "azure.resource_group.name": TEST_WEBSITE_RESOURCE_GROUP,
            },
            "WEBSITE_RESOURCE_GROUP": {
                "service.name": TEST_WEBSITE_SITE_NAME,
                "cloud.account.id": TEST_SUBSCRIPTION_ID,
            },
            "WEBSITE_SITE_NAME": {
                "cloud.account.id": TEST_SUBSCRIPTION_ID,
                "azure.resource_group.name": TEST_WEBSITE_RESOURCE_GROUP,
            },
        }
        omitted_attributes = {
            "WEBSITE_OWNER_NAME": {"cloud.account.id", "cloud.resource_id"},
            "WEBSITE_RESOURCE_GROUP": {"azure.resource_group.name", "cloud.resource_id"},
            "WEBSITE_SITE_NAME": {"service.name", "cloud.resource_id"},
        }

        for missing_environment_variable, expected in expected_attributes.items():
            with self.subTest(missing_environment_variable=missing_environment_variable):
                environment = TEST_FUNCTIONS_ENVIRONMENT.copy()
                del environment[missing_environment_variable]
                with patch.dict("os.environ", environment, clear=True):
                    attributes = AzureFunctionsResourceDetector().detect().attributes

                self.assertEqual(attributes["cloud.provider"], "azure")
                self.assertEqual(attributes["cloud.platform"], "azure_functions")
                self.assertEqual(attributes["cloud.region"], TEST_REGION_NAME)
                self.assertEqual(attributes["faas.instance"], TEST_WEBSITE_INSTANCE_ID)
                self.assertEqual(attributes["faas.max_memory"], 1024)
                for key, value in expected.items():
                    self.assertEqual(attributes[key], value)
                for key in omitted_attributes[missing_environment_variable]:
                    self.assertNotIn(key, attributes)

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
