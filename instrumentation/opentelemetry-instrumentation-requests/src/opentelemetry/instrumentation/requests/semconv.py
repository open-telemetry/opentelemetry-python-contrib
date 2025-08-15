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
Semantic conventions for user agent synthetic type detection.

This module defines constants for user agent synthetic type attributes and values
according to OpenTelemetry semantic conventions.

**EXPERIMENTAL**: This module contains experimental semantic conventions that are not
yet part of the official OpenTelemetry semantic conventions specification. These
attributes and values may experience breaking changes in future versions as the
specification evolves.

The semantic conventions defined here are used to classify synthetic traffic based
on User-Agent header analysis, helping distinguish between:
- Bot traffic (web crawlers, search engine bots)
- Test traffic (monitoring systems, health checks)
- Regular user traffic

These experimental conventions may be:
1. Modified with different attribute names or values
2. Moved to official semantic convention packages
3. Deprecated in favor of standardized alternatives
4. Changed based on community feedback and specification updates

Users should be prepared for potential breaking changes when upgrading and should
monitor OpenTelemetry specification updates for official semantic convention releases.
"""

# User agent synthetic type attribute
ATTR_USER_AGENT_SYNTHETIC_TYPE = "user_agent.synthetic.type"

# User agent synthetic type values
USER_AGENT_SYNTHETIC_TYPE_VALUE_BOT = "bot"
USER_AGENT_SYNTHETIC_TYPE_VALUE_TEST = "test"
