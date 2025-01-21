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


"""Provides utilities for automatic content-type detection."""


# Helper used to handle the possibility of optional 'magic' dependency
# being unavailable for guessing the MIME type of raw bytes.
class _FallBackModule:
    """Class that is shaped like the portion of 'magic' we need."""

    def from_buffer(self, raw_bytes: bytes, mime: bool = True):
        """Fallback, subpar implementation of 'from_buffer'."""
        return "application/octet-stream"


# Set up '_module' to either use 'magic' or the fallback.
_module = _FallBackModule()
try:
    import magic

    _module = magic
except ImportError:
    pass


def detect_content_type(raw_bytes: bytes) -> str:
    """Attempts to infer the content type of the specified data."""
    if not raw_bytes:
        return "application/octet-stream"
    return _module.from_buffer(raw_bytes, mime=True)
