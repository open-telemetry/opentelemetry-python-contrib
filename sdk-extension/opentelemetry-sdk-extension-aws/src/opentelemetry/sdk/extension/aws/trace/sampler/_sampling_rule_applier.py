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

# Includes work from:
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from threading import Lock
from typing import Sequence
from urllib.parse import urlparse

# pylint: disable=no-name-in-module
from opentelemetry.context import Context
from opentelemetry.sdk.extension.aws.trace.sampler._clock import _Clock
from opentelemetry.sdk.extension.aws.trace.sampler._matcher import (
    _Matcher,
    cloud_platform_mapping,
)
from opentelemetry.sdk.extension.aws.trace.sampler._rate_limiting_sampler import (
    _RateLimitingSampler,
)
from opentelemetry.sdk.extension.aws.trace.sampler._sampling_rule import (
    _SamplingRule,
)
from opentelemetry.sdk.extension.aws.trace.sampler._sampling_statistics_document import (
    _SamplingStatisticsDocument,
)
from opentelemetry.sdk.extension.aws.trace.sampler._sampling_target import (
    _SamplingTarget,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.sampling import (
    Decision,
    Sampler,
    SamplingResult,
    TraceIdRatioBased,
)
from opentelemetry.semconv.resource import (
    CloudPlatformValues,
    ResourceAttributes,
)
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import Link, SpanKind
from opentelemetry.trace.span import TraceState
from opentelemetry.util.types import Attributes, AttributeValue


class _SamplingRuleApplier:
    def __init__(
        self,
        sampling_rule: _SamplingRule,
        client_id: str,
        clock: _Clock,
        statistics: _SamplingStatisticsDocument | None = None,
        target: _SamplingTarget | None = None,
    ):
        self.__client_id = client_id
        self._clock = clock
        self.sampling_rule = sampling_rule

        if statistics is None:
            self.__statistics = _SamplingStatisticsDocument(
                self.__client_id, self.sampling_rule.RuleName
            )
        else:
            self.__statistics = statistics
        self.__statistics_lock = Lock()

        self.__borrowing = False

        if target is None:
            self.__fixed_rate_sampler = TraceIdRatioBased(
                self.sampling_rule.FixedRate
            )
            # Until targets are fetched, initialize as borrowing=True if there will be a quota > 0
            if self.sampling_rule.ReservoirSize > 0:
                self.__reservoir_sampler = self.__create_reservoir_sampler(
                    quota=1
                )
                self.__borrowing = True
            else:
                self.__reservoir_sampler = self.__create_reservoir_sampler(
                    quota=0
                )
            # No targets are present, borrow until the end of time if there is any quota
            self.__reservoir_expiry = self._clock.max()
        else:
            new_quota = (
                target.ReservoirQuota
                if target.ReservoirQuota is not None
                else 0
            )
            new_fixed_rate = target.FixedRate
            self.__reservoir_sampler = self.__create_reservoir_sampler(
                quota=new_quota
            )
            self.__fixed_rate_sampler = TraceIdRatioBased(new_fixed_rate)
            if target.ReservoirQuotaTTL is not None:
                self.__reservoir_expiry = self._clock.from_timestamp(
                    target.ReservoirQuotaTTL
                )
            else:
                # assume expired if no TTL
                self.__reservoir_expiry = self._clock.now()

    def should_sample(
        self,
        parent_context: Context | None,
        trace_id: int,
        name: str,
        kind: SpanKind | None = None,
        attributes: Attributes | None = None,
        links: Sequence["Link"] | None = None,
        trace_state: TraceState | None = None,
    ) -> "SamplingResult":
        has_borrowed = False
        has_sampled = False
        sampling_result = SamplingResult(
            decision=Decision.DROP,
            attributes=attributes,
            trace_state=trace_state,
        )

        reservoir_expired: bool = self._clock.now() >= self.__reservoir_expiry
        if not reservoir_expired:
            sampling_result = self.__reservoir_sampler.should_sample(
                parent_context,
                trace_id,
                name,
                kind=kind,
                attributes=attributes,
                links=links,
                trace_state=trace_state,
            )

        if sampling_result.decision is not Decision.DROP:
            has_borrowed = self.__borrowing
            has_sampled = True
        else:
            sampling_result = self.__fixed_rate_sampler.should_sample(
                parent_context,
                trace_id,
                name,
                kind=kind,
                attributes=attributes,
                links=links,
                trace_state=trace_state,
            )
            if sampling_result.decision is not Decision.DROP:
                has_sampled = True

        with self.__statistics_lock:
            self.__statistics.RequestCount += 1
            self.__statistics.BorrowCount += 1 if has_borrowed else 0
            self.__statistics.SampleCount += 1 if has_sampled else 0

        return sampling_result

    def get_then_reset_statistics(self):
        with self.__statistics_lock:
            old_stats = self.__statistics
            self.__statistics = _SamplingStatisticsDocument(
                self.__client_id, self.sampling_rule.RuleName
            )

        return old_stats.snapshot(self._clock)

    def with_target(self, target: _SamplingTarget) -> "_SamplingRuleApplier":
        new_applier = _SamplingRuleApplier(
            self.sampling_rule,
            self.__client_id,
            self._clock,
            self.__statistics,
            target,
        )
        return new_applier

    def matches(self, resource: Resource, attributes: Attributes) -> bool:
        url_path: AttributeValue | None = None
        url_full: AttributeValue | None = None
        http_request_method: AttributeValue | None = None
        server_address: AttributeValue | None = None
        service_name: AttributeValue | None = None

        if attributes is not None:
            # If `URL_PATH/URL_FULL/HTTP_REQUEST_METHOD/SERVER_ADDRESS` are not populated
            # also check `HTTP_TARGET/HTTP_URL/HTTP_METHOD/HTTP_HOST` respectively as backup
            url_path = attributes.get(
                SpanAttributes.URL_PATH,
                attributes.get(SpanAttributes.HTTP_TARGET, None),
            )
            url_full = attributes.get(
                SpanAttributes.URL_FULL,
                attributes.get(SpanAttributes.HTTP_URL, None),
            )
            http_request_method = attributes.get(
                SpanAttributes.HTTP_REQUEST_METHOD,
                attributes.get(SpanAttributes.HTTP_METHOD, None),
            )
            server_address = attributes.get(
                SpanAttributes.SERVER_ADDRESS,
                attributes.get(SpanAttributes.HTTP_HOST, None),
            )

        # Resource shouldn't be none as it should default to empty resource
        if resource is not None:
            service_name = resource.attributes.get(
                ResourceAttributes.SERVICE_NAME, ""
            )

        # target may be in url
        if url_path is None and isinstance(url_full, str):
            scheme_end_index = url_full.find("://")
            # For network calls, URL usually has `scheme://host[:port][path][?query][#fragment]` format
            # Per spec, url.full is always populated with scheme://
            # If scheme is not present, assume it's bad instrumentation and ignore.
            if scheme_end_index > -1:
                # urlparse("scheme://netloc/path;parameters?query#fragment")
                url_path = urlparse(url_full).path
                if url_path == "":
                    url_path = "/"
        elif url_path is None and url_full is None:
            # When missing, the URL Path is assumed to be /
            url_path = "/"

        return (
            _Matcher.attribute_match(attributes, self.sampling_rule.Attributes)
            and _Matcher.wild_card_match(url_path, self.sampling_rule.URLPath)
            and _Matcher.wild_card_match(
                http_request_method, self.sampling_rule.HTTPMethod
            )
            and _Matcher.wild_card_match(
                server_address, self.sampling_rule.Host
            )
            and _Matcher.wild_card_match(
                service_name, self.sampling_rule.ServiceName
            )
            and _Matcher.wild_card_match(
                self.__get_service_type(resource),
                self.sampling_rule.ServiceType,
            )
            and _Matcher.wild_card_match(
                self.__get_arn(resource, attributes),
                self.sampling_rule.ResourceARN,
            )
        )

    def __create_reservoir_sampler(self, quota: int) -> Sampler:
        return _RateLimitingSampler(quota, self._clock)

    # pylint: disable=no-self-use
    def __get_service_type(self, resource: Resource) -> str:
        if resource is None:
            return ""

        cloud_platform = resource.attributes.get(
            ResourceAttributes.CLOUD_PLATFORM, None
        )
        if not isinstance(cloud_platform, str):
            return ""

        return cloud_platform_mapping.get(cloud_platform, "")

    def __get_arn(
        self, resource: Resource, attributes: Attributes
    ) -> AttributeValue:
        if resource is not None:
            arn = resource.attributes.get(
                ResourceAttributes.AWS_ECS_CONTAINER_ARN, None
            )
            if arn is not None:
                return arn
        if (
            resource is not None
            and resource.attributes.get(ResourceAttributes.CLOUD_PLATFORM)
            == CloudPlatformValues.AWS_LAMBDA.value
        ):
            return self.__get_lambda_arn(resource, attributes)
        return ""

    def __get_lambda_arn(
        self, resource: Resource, attributes: Attributes
    ) -> AttributeValue:
        arn = resource.attributes.get(
            ResourceAttributes.CLOUD_RESOURCE_ID,
            resource.attributes.get(ResourceAttributes.FAAS_ID, None),
        )
        if arn is not None:
            return arn

        if attributes is None:
            return ""

        # Note from `SpanAttributes.CLOUD_RESOURCE_ID`:
        # "On some cloud providers, it may not be possible to determine the full ID at startup,
        # so it may be necessary to set cloud.resource_id as a span attribute instead."
        arn = attributes.get(
            SpanAttributes.CLOUD_RESOURCE_ID, attributes.get("faas.id", None)
        )
        if arn is not None:
            return arn

        return ""
