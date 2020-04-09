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

from opentelemetry.instrumentation.redis import constants

VALUE_PLACEHOLDER = "?"
VALUE_MAX_LEN = 100
VALUE_TOO_LONG_MARK = "..."
CMD_MAX_LEN = 1000
TARGET_HOST = "out.host"
TARGET_PORT = "out.port"


def _extract_conn_attributes(conn_kwargs):
    """ Transform redis conn info into dogtrace metas """
    try:
        return {
            TARGET_HOST: conn_kwargs["host"],
            TARGET_PORT: conn_kwargs["port"],
            constants.DB: conn_kwargs["db"] or 0,
        }
    except Exception:  # pylint: disable=broad-except
        return {}


def format_command_args(args):
    """Format a command by removing unwanted values

    Restrict what we keep from the values sent (with a SET, HGET, LPUSH, ...):
      - Skip binary content
      - Truncate
    """
    length = 0
    out = []
    for arg in args:
        try:
            cmd = str(arg)

            if len(cmd) > VALUE_MAX_LEN:
                cmd = cmd[:VALUE_MAX_LEN] + VALUE_TOO_LONG_MARK

            if length + len(cmd) > CMD_MAX_LEN:
                prefix = cmd[: CMD_MAX_LEN - length]
                out.append("%s%s" % (prefix, VALUE_TOO_LONG_MARK))
                break

            out.append(cmd)
            length += len(cmd)
        except Exception:  # pylint: disable=broad-except
            out.append(VALUE_PLACEHOLDER)
            break

    return " ".join(out)
