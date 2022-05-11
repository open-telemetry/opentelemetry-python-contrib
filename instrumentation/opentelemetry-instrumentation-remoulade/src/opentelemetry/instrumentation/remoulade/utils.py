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


def attach_span(span_registry, message_id, span, is_publish=False):
    span_registry[(message_id, is_publish)] = span


def detach_span(span_registry, message_id, is_publish=False):
    span_registry.pop((message_id, is_publish))


def retrieve_span(span_registry, message_id, is_publish=False):
    return span_registry.get((message_id, is_publish), (None, None))
