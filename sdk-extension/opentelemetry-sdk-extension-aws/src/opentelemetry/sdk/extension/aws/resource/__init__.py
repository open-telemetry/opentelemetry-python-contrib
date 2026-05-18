# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
# pylint:disable=no-name-in-module

from opentelemetry.sdk.extension.aws.resource._lambda import (
    AwsLambdaResourceDetector,
)
from opentelemetry.sdk.extension.aws.resource.beanstalk import (
    AwsBeanstalkResourceDetector,
)
from opentelemetry.sdk.extension.aws.resource.ec2 import AwsEc2ResourceDetector
from opentelemetry.sdk.extension.aws.resource.ecs import AwsEcsResourceDetector
from opentelemetry.sdk.extension.aws.resource.eks import AwsEksResourceDetector

__all__ = [
    "AwsBeanstalkResourceDetector",
    "AwsEc2ResourceDetector",
    "AwsEcsResourceDetector",
    "AwsEksResourceDetector",
    "AwsLambdaResourceDetector",
]
