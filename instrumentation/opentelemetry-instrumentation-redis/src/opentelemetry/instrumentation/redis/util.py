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
Some utils used by the redis integration
"""
from opentelemetry.semconv.trace import (
    DbSystemValues,
    NetTransportValues,
    SpanAttributes,
)


def _extract_conn_attributes(conn_kwargs):
    """Transform redis conn info into dict"""
    attributes = {
        SpanAttributes.DB_SYSTEM: DbSystemValues.REDIS.value,
    }
    db = conn_kwargs.get("db", 0)
    attributes[SpanAttributes.DB_REDIS_DATABASE_INDEX] = db
    if "path" in conn_kwargs:
        attributes[SpanAttributes.NET_PEER_NAME] = conn_kwargs.get("path", "")
        attributes[SpanAttributes.NET_TRANSPORT] = (
            NetTransportValues.OTHER.value
        )
    else:
        attributes[SpanAttributes.NET_PEER_NAME] = conn_kwargs.get(
            "host", "localhost"
        )
        attributes[SpanAttributes.NET_PEER_PORT] = conn_kwargs.get(
            "port", 6379
        )
        attributes[SpanAttributes.NET_TRANSPORT] = (
            NetTransportValues.IP_TCP.value
        )

    return attributes


def _format_command_args(args):
    """Format and sanitize command arguments, and trim them as needed"""
    cmd_max_len = 1000
    value_too_long_mark = "..."

    # Sanitized query format: "COMMAND ? ?"
    args_length = len(args)
    if args_length > 0:
        out = [str(args[0])] + ["?"] * (args_length - 1)
        out_str = " ".join(out)

        if len(out_str) > cmd_max_len:
            out_str = (
                out_str[: cmd_max_len - len(value_too_long_mark)]
                + value_too_long_mark
            )
    else:
        out_str = ""

    return out_str
