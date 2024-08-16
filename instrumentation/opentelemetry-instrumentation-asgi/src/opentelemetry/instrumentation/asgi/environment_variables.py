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
Exclude the http send span from the tracing feature in Python.
"""

OTEL_PYTHON_ASGI_EXCLUDE_SEND_SPAN = "OTEL_PYTHON_ASGI_EXCLUDE_SEND_SPAN"

"""
Exclude the http receive span from the tracing feature in Python.
"""
OTEL_PYTHON_ASGI_EXCLUDE_RECEIVE_SPAN = "OTEL_PYTHON_ASGI_EXCLUDE_RECEIVE_SPAN"
