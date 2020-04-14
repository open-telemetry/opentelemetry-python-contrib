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


def _extract_conn_attributes(conn_kwargs):
    """ Transform redis conn info into dict """
    try:
        return {
            "out.host": conn_kwargs["host"],
            "out.port": conn_kwargs["port"],
            "out.redis_db": conn_kwargs["db"] or 0,
        }
    except KeyError:
        return {}


def format_command_args(args):
    """Format a command by removing unwanted values

    Restrict what we keep from the values sent (with a SET, HGET, LPUSH, ...):
      - Skip binary content
      - Truncate
    """
    value_placeholder = "?"
    value_max_len = 100
    value_too_long_mark = "..."
    cmd_max_len = 1000
    length = 0
    out = []
    for arg in args:
        try:
            cmd = str(arg)

            if len(cmd) > value_max_len:
                cmd = cmd[:value_max_len] + value_too_long_mark

            if length + len(cmd) > cmd_max_len:
                prefix = cmd[: cmd_max_len - length]
                out.append("%s%s" % (prefix, value_too_long_mark))
                break

            out.append(cmd)
            length += len(cmd)
        except Exception:  # pylint: disable=broad-except
            out.append(value_placeholder)
            break

    return " ".join(out)
