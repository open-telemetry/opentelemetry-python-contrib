# Copyright 2020, OpenTelemetry Authors
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

from enum import Enum


class HTTPMethod(Enum):
    """HTTP methods and descriptions"""

    def __repr__(self):
        return self.value[0]

    CONNECT = 'CONNECT', 'Establish a connection to the server.'
    DELETE = 'DELETE', 'Remove the target.'
    GET = 'GET', 'Retrieve the target.'
    HEAD = 'HEAD', 'Same as GET, but only retrieve the status line and header section.'
    OPTIONS = 'OPTIONS', 'Describe the communication options for the target.'
    PATCH = 'PATCH', 'Apply partial modifications to a target.'
    POST = 'POST', 'Perform target-specific processing with the request payload.'
    PUT = 'PUT', 'Replace the target with the request payload.'
    TRACE = 'TRACE', 'Perform a message loop-back test along the path to the target.'
