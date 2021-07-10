# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import logging
import os
from opentelemetry.sdk.resources import (
    Resource,
    ResourceDetector,
)
from opentelemetry.semconv.resource import (
    CloudInfrastructureServiceValues,
    CloudProviderValues,
    ResourceAttributes,
)

logger = logging.getLogger(__name__)


class AwsBeanstalkDetector(ResourceDetector):
    def detect(self) -> "Resource":
        if os.name == "nt":
            CONF_FILE_PATH = "C:\\Program Files\\Amazon\\XRay\\environment.conf"
        else:
            CONF_FILE_PATH = "/var/elasticbeanstalk/xray/environment.conf"

        try:
            with open(CONF_FILE_PATH) as f:
                parsed_data = json.load(f)
            # NOTE: (NathanielRN) Should ResourceDetectors use Resource.detect() to pull in the environment variable?
            # `OTELResourceDetector` doesn't do this...
        except Exception as e:
            logger.debug(f"AwsBeanstalkDetector failed: {e}")
            return Resource.get_empty()
        return Resource(
            {
                ResourceAttributes.CLOUD_PROVIDER: CloudProviderValues.AWS,
                ResourceAttributes.CLOUD_PLATFORM: CloudInfrastructureServiceValues.AWS_ELASTICBEANSTALK,
                ResourceAttributes.SERVICE_NAME: CloudInfrastructureServiceValues.AWS_ELASTICBEANSTALK,
                ResourceAttributes.SERVICE_NAMESPACE: parsed_data[
                    "environment_name"
                ]
                or "",
                ResourceAttributes.SERVICE_VERSION: parsed_data["version_label"]
                or "",
                ResourceAttributes.SERVICE_INSTANCE_ID: parsed_data[
                    "deployment_id"
                ]
                or "",
            }
        )
