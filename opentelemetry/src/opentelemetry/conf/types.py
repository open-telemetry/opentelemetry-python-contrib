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
#

"""
OpenTelemetry SDK configuration helpers
"""

from typing import Any, Callable, Optional, Sequence, Union, cast

from typing_extensions import Protocol

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import (
    ConcurrentMultiSpanProcessor,
    SpanLimits,
    SpanProcessor,
    SynchronousMultiSpanProcessor,
    TracerProvider,
)
from opentelemetry.sdk.trace.export import SpanExporter
from opentelemetry.sdk.trace.id_generator import IdGenerator
from opentelemetry.sdk.trace.sampling import Sampler


class TracerProviderFactory(Protocol):
    def __call__(
        self,
        sampler: Optional[Sampler],
        resource: Optional[Resource],
        shutdown_on_exit: Optional[bool],
        active_span_processor: Optional[
            Union[SynchronousMultiSpanProcessor, ConcurrentMultiSpanProcessor]
        ],
        id_generator: Optional[IdGenerator],
        span_limits: Optional[SpanLimits],
        *args: Sequence[Any],
        **kwargs: Sequence[Any],
    ) -> TracerProvider:
        pass


class SpanProcessorFactory(Protocol):
    def __call__(
        self,
        exporter: SpanExporter,
        *args: Sequence[Any],
        **kwargs: Sequence[Any],
    ) -> SpanProcessor:
        pass


SpanExporterFactory = Callable[..., SpanExporter]
