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

import os

from typing import Literal, Union

from opentelemetry.instrumentation.fastapi.environment_variables import (
    OTEL_PYTHON_FASTAPI_EXCLUDE_SPANS,
)

SpanType = Literal["receive", "send"]


def get_excluded_spans() -> Union[list[SpanType], None]:
    raw = os.getenv(OTEL_PYTHON_FASTAPI_EXCLUDE_SPANS)

    if not raw:
        return None

    values = [v.strip() for v in raw.split(",") if v.strip()]

    allowed: set[str] = {"receive", "send"}
    result: list[SpanType] = []

    for value in values:
        if value not in allowed:
            raise ValueError(
                f"Invalid excluded span: '{value}'. Allowed values are: {allowed}"
            )
        result.append(value)  # type: ignore[arg-type]

    return result
