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

# """
# Defines the instrumentation metrics and instruments for OpenAI Agents.
# """

# from typing import Dict, List

# # Define the instruments that this package provides
# INSTRUMENTS = {
#     "openai_agents.request.duration": {
#         "name": "gen_ai.client.operation.duration",
#         "description": "Duration of OpenAI agents operations",
#         "unit": "s",
#         "instrument_type": "histogram",
#     },
#     "openai_agents.request.tokens": {
#         "name": "gen_ai.client.token.usage",
#         "description": "Number of tokens used in OpenAI agents operations",
#         "unit": "token",
#         "instrument_type": "counter",
#     },
# }


# def get_instruments() -> Dict[str, Dict[str, str]]:
#     """Get all instruments defined by this package."""
#     return INSTRUMENTS


# def get_instrument_names() -> List[str]:
#     """Get all instrument names defined by this package."""
#     return list(INSTRUMENTS.keys())
