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

import random
from logging import getLogger
from threading import Timer
from typing import Optional, Sequence

from typing_extensions import override

# pylint: disable=no-name-in-module
from opentelemetry.context import Context
from opentelemetry.sdk.extension.aws.trace.sampler._aws_xray_sampling_client import (
    DEFAULT_SAMPLING_PROXY_ENDPOINT,
    _AwsXRaySamplingClient,
)
from opentelemetry.sdk.extension.aws.trace.sampler._clock import _Clock
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.sampling import (
    Decision,
    ParentBased,
    Sampler,
    SamplingResult,
)
from opentelemetry.trace import Link, SpanKind
from opentelemetry.trace.span import TraceState
from opentelemetry.util.types import Attributes

_logger = getLogger(__name__)

DEFAULT_RULES_POLLING_INTERVAL_SECONDS = 300


# WORK IN PROGRESS
# TODO: Rename to AwsXRayRemoteSampler when the implementation is complete and is ready to use
#
# Wrapper class to ensure that all XRay Sampler Functionality in _InternalAwsXRayRemoteSampler
# uses ParentBased logic to respect the parent span's sampling decision
class _AwsXRayRemoteSampler(Sampler):
    def __init__(
        self,
        resource: Resource,
        endpoint: Optional[str] = None,
        polling_interval: Optional[int] = None,
        log_level: Optional[str] = None,
    ):
        self._root = ParentBased(
            _InternalAwsXRayRemoteSampler(
                resource=resource,
                endpoint=endpoint,
                polling_interval=polling_interval,
                log_level=log_level,
            )
        )

    @override
    def should_sample(
        self,
        parent_context: Optional["Context"],
        trace_id: int,
        name: str,
        kind: Optional[SpanKind] = None,
        attributes: Optional[Attributes] = None,
        links: Optional[Sequence["Link"]] = None,
        trace_state: Optional["TraceState"] = None,
    ) -> "SamplingResult":
        return self._root.should_sample(
            parent_context,
            trace_id,
            name,
            kind=kind,
            attributes=attributes,
            links=links,
            trace_state=trace_state,
        )

    # pylint: disable=no-self-use
    @override
    def get_description(self) -> str:
        return f"AwsXRayRemoteSampler{{root:{self._root.get_description()}}}"


# WORK IN PROGRESS
#
# _InternalAwsXRayRemoteSampler contains all core XRay Sampler Functionality,
# however it is NOT Parent-based (e.g. Sample logic runs for each span)
# Not intended for external use, use Parent-based `AwsXRayRemoteSampler` instead.
class _InternalAwsXRayRemoteSampler(Sampler):
    """
    Remote Sampler for OpenTelemetry that gets sampling configurations from AWS X-Ray

    Args:
        resource: OpenTelemetry Resource (Required)
        endpoint: proxy endpoint for AWS X-Ray Sampling (Optional)
        polling_interval: Polling interval for getSamplingRules call (Optional)
        log_level: custom log level configuration for remote sampler (Optional)
    """

    def __init__(
        self,
        resource: Resource,
        endpoint: Optional[str] = None,
        polling_interval: Optional[int] = None,
        log_level: Optional[str] = None,
    ):
        # Override default log level
        if log_level is not None:
            _logger.setLevel(log_level)

        if endpoint is None:
            _logger.info(
                "`endpoint` is `None`. Defaulting to %s",
                DEFAULT_SAMPLING_PROXY_ENDPOINT,
            )
            endpoint = DEFAULT_SAMPLING_PROXY_ENDPOINT
        if polling_interval is None or polling_interval < 10:
            _logger.info(
                "`polling_interval` is `None` or too small. Defaulting to %s",
                DEFAULT_RULES_POLLING_INTERVAL_SECONDS,
            )
            polling_interval = DEFAULT_RULES_POLLING_INTERVAL_SECONDS

        self.__client_id = self.__generate_client_id()  # pylint: disable=W0238
        self._clock = _Clock()
        self.__xray_client = _AwsXRaySamplingClient(
            endpoint, log_level=log_level
        )

        self.__polling_interval = polling_interval
        self.__rule_polling_jitter = random.uniform(0.0, 5.0)

        if resource is not None:
            self.__resource = resource  # pylint: disable=W0238
        else:
            _logger.warning(
                "OTel Resource provided is `None`. Defaulting to empty resource"
            )
            self.__resource = Resource.get_empty()  # pylint: disable=W0238

        # Schedule the next rule poll now
        # Python Timers only run once, so they need to be recreated for every poll
        self._rules_timer = Timer(0, self.__start_sampling_rule_poller)
        self._rules_timer.daemon = True  # Ensures that when the main thread exits, the Timer threads are killed
        self._rules_timer.start()

        # (TODO) set up the target poller to go off once after the default interval. Subsequent polls may use new intervals.

    # pylint: disable=no-self-use
    @override
    def should_sample(
        self,
        parent_context: Optional["Context"],
        trace_id: int,
        name: str,
        kind: Optional[SpanKind] = None,
        attributes: Optional[Attributes] = None,
        links: Optional[Sequence["Link"]] = None,
        trace_state: Optional["TraceState"] = None,
    ) -> "SamplingResult":
        return SamplingResult(
            decision=Decision.DROP,
            attributes=attributes,
            trace_state=trace_state,
        )

    # pylint: disable=no-self-use
    @override
    def get_description(self) -> str:
        description = (
            "_InternalAwsXRayRemoteSampler{remote sampling with AWS X-Ray}"
        )
        return description

    def __get_and_update_sampling_rules(self) -> None:
        sampling_rules = self.__xray_client.get_sampling_rules()  # pylint: disable=W0612  # noqa: F841
        # (TODO) update rules cache with sampling rules

    def __start_sampling_rule_poller(self) -> None:
        self.__get_and_update_sampling_rules()
        # Schedule the next sampling rule poll
        self._rules_timer = Timer(
            self.__polling_interval + self.__rule_polling_jitter,
            self.__start_sampling_rule_poller,
        )
        self._rules_timer.daemon = True
        self._rules_timer.start()

    def __generate_client_id(self) -> str:
        hex_chars = "0123456789abcdef"
        client_id_array: list[str] = []
        for _ in range(0, 24):
            client_id_array.append(random.choice(hex_chars))
        return "".join(client_id_array)
