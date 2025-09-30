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


class Config:
    """
    Shared static config for LangChain OTel instrumentation.
    """

    # Logger to handle exceptions during instrumentation
    exception_logger = None

    # Globally suppress instrumentation
    _suppress_instrumentation = False

    @classmethod
    def suppress_instrumentation(cls, suppress: bool = True):
        cls._suppress_instrumentation = suppress

    @classmethod
    def is_instrumentation_suppressed(cls) -> bool:
        return cls._suppress_instrumentation
