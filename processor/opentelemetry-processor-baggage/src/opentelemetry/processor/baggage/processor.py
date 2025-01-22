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

from typing import Callable, Optional

from opentelemetry.baggage import get_all as get_all_baggage
from opentelemetry.context import Context
from opentelemetry.sdk.trace.export import SpanProcessor
from opentelemetry.trace import Span

# A BaggageKeyPredicate is a function that takes a baggage key and returns a boolean
BaggageKeyPredicateT = Callable[[str], bool]

# A BaggageKeyPredicate that always returns True, allowing all baggage keys to be added to spans
ALLOW_ALL_BAGGAGE_KEYS: BaggageKeyPredicateT = lambda _: True  # noqa: E731


class BaggageSpanProcessor(SpanProcessor):
    """
    The BaggageSpanProcessor reads entries stored in Baggage
    from the parent context and adds the baggage entries' keys and
    values to the span as attributes on span start.

    Add this span processor to a tracer provider.

    Keys and values added to Baggage will appear on subsequent child
    spans for a trace within this service *and* be propagated to external
    services in accordance with any configured propagation formats
    configured. If the external services also have a Baggage span
    processor, the keys and values will appear in those child spans as
    well.

    ⚠ Warning ⚠️

    Do not put sensitive information in Baggage.

    To repeat: a consequence of adding data to Baggage is that the keys and
    values will appear in all outgoing HTTP headers from the application.

    """

    def __init__(self, baggage_key_predicate: BaggageKeyPredicateT) -> None:
        self._baggage_key_predicate = baggage_key_predicate

    def on_start(
        self, span: "Span", parent_context: Optional[Context] = None
    ) -> None:
        baggage = get_all_baggage(parent_context)
        for key, value in baggage.items():
            if self._baggage_key_predicate(key):
                span.set_attribute(key, value)
