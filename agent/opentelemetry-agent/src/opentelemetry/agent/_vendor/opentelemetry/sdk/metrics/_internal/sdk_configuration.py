# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# pylint: disable=unused-import

from collections.abc import Sequence
from dataclasses import dataclass

# This kind of import is needed to avoid Sphinx errors.
import opentelemetry.agent._vendor.opentelemetry.sdk.metrics
from opentelemetry.agent._vendor import opentelemetry
import opentelemetry.agent._vendor.opentelemetry.sdk.resources
from opentelemetry.agent._vendor import opentelemetry


@dataclass
class SdkConfiguration:
    exemplar_filter: "opentelemetry.sdk.metrics.ExemplarFilter"
    resource: "opentelemetry.sdk.resources.Resource"
    views: Sequence["opentelemetry.sdk.metrics.view.View"]
