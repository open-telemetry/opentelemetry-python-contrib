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

"""
Labeler that supports per-request custom attribute addition to web framework
instrumentor-originating OpenTelemetry metrics.

This was inspired by OpenTelemetry Go's net/http instrumentation Labeler
https://github.com/open-telemetry/opentelemetry-go-contrib/pull/306
"""

from opentelemetry.instrumentation._labeler._internal import (
    Labeler,
    clear_labeler,
    enhance_metric_attributes,
    get_labeler,
    get_labeler_attributes,
    set_labeler,
)

__all__ = [
    "Labeler",
    "get_labeler",
    "set_labeler",
    "clear_labeler",
    "get_labeler_attributes",
    "enhance_metric_attributes",
]
