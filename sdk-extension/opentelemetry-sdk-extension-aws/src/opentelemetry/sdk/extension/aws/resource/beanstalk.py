# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import json
import logging
import os

from opentelemetry.sdk.resources import Resource, ResourceDetector
from opentelemetry.semconv.resource import (
    CloudPlatformValues,
    CloudProviderValues,
    ResourceAttributes,
)

logger = logging.getLogger(__name__)


class AwsBeanstalkResourceDetector(ResourceDetector):
    """Detects attribute values only available when the app is running on AWS
    Elastic Beanstalk and returns them in a Resource.

    NOTE: Requires enabling X-Ray on Beanstalk Environment. See more here: https://docs.aws.amazon.com/xray/latest/devguide/xray-services-beanstalk.html
    """

    def detect(self) -> "Resource":
        if os.name == "nt":
            conf_file_path = (
                "C:\\Program Files\\Amazon\\XRay\\environment.conf"
            )
        else:
            conf_file_path = "/var/elasticbeanstalk/xray/environment.conf"

        if not os.path.exists(conf_file_path):
            return Resource.get_empty()

        try:
            with open(conf_file_path, encoding="utf-8") as conf_file:
                parsed_data = json.load(conf_file)

            return Resource(
                {
                    ResourceAttributes.CLOUD_PROVIDER: CloudProviderValues.AWS.value,
                    ResourceAttributes.CLOUD_PLATFORM: CloudPlatformValues.AWS_ELASTIC_BEANSTALK.value,
                    ResourceAttributes.SERVICE_NAME: CloudPlatformValues.AWS_ELASTIC_BEANSTALK.value,
                    ResourceAttributes.SERVICE_INSTANCE_ID: parsed_data[
                        "deployment_id"
                    ],
                    ResourceAttributes.SERVICE_NAMESPACE: parsed_data[
                        "environment_name"
                    ],
                    ResourceAttributes.SERVICE_VERSION: parsed_data[
                        "version_label"
                    ],
                }
            )
        # pylint: disable=broad-except
        except Exception as exception:
            if self.raise_on_error:
                raise exception

            logger.warning("%s failed: %s", self.__class__.__name__, exception)
            return Resource.get_empty()
