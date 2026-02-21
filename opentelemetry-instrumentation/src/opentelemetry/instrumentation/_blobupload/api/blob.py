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

import base64
import json
from types import MappingProxyType as _frozendict
from typing import Mapping, Optional


class Blob:
    """Represents an opaque binary object and associated metadata.

    This object conteptually has the following properties:

      - raw_bytes: the actual data (payload) of the Blob
      - content_type: metadata about the content type (e.g. "image/jpeg")
      - labels: key/value data that can be used to identify and contextualize
         the object such as {"trace_id": "...", "span_id": "...", "filename": ...}
    """

    def __init__(
        self,
        raw_bytes: bytes,
        content_type: Optional[str] = None,
        labels: Optional[Mapping[str, str]] = None,
    ):
        """Initialize the blob with an explicit set of properties.

        Args:
          raw_bytes: the required payload
          content_type: the MIME type describing the type of data in the payload
          labels: additional key/value data about the Blob
        """
        self._raw_bytes = raw_bytes
        self._content_type = content_type
        self._labels = {}
        if labels is not None:
            if isinstance(labels, dict):
                self._labels.update(labels)
            else:
                for k in labels:
                    self._labels[k] = labels[k]

    @staticmethod
    def from_data_uri(uri: str, labels: Optional[Mapping[str, str]] = None) -> "Blob":
        """Instantiate a blob from a 'data:...' URI.

        Args:
            uri: A URI in the 'data:' format. Supports a subset of 'data:' URIs
              that encode the data with the 'base64' extension and that include
              a content type. Should work with any normal 'image/jpeg', 'image/png',
              'application/pdf', 'audio/aac', and many others. DOES NOT SUPPORT
              encoding data as percent-encoded text (no "base64").

            labels: Additional key/value data to include in the constructed Blob.
        """
        if not uri.startswith("data:"):
            raise ValueError(
                'Invalid "uri"; expected "data:" prefix. Found: "{}"'.format(
                    uri
                )
            )
        if ";base64," not in uri:
            raise ValueError(
                'Invalid "uri"; expected ";base64," section. Found: "{}"'.format(
                    uri
                )
            )
        data_prefix_len = len("data:")
        after_data_prefix = uri[data_prefix_len:]
        if ";" not in after_data_prefix:
            raise ValueError(
                'Invalid "uri"; expected ";" in URI. Found: "{}"'.format(uri)
            )
        content_type, remaining = after_data_prefix.split(";", 1)
        while not remaining.startswith("base64,"):
            _, remaining = remaining.split(";", 1)
        assert remaining.startswith("base64,")
        base64_len = len("base64,")
        base64_encoded_content = remaining[base64_len:]
        raw_bytes = base64.b64decode(base64_encoded_content)
        return Blob(raw_bytes, content_type=content_type, labels=labels)

    @property
    def raw_bytes(self) -> bytes:
        """Returns the raw bytes (payload) of this Blob."""
        return self._raw_bytes

    @property
    def content_type(self) -> Optional[str]:
        """Returns the content type (or None) of this Blob."""
        return self._content_type

    @property
    def labels(self) -> Mapping[str, str]:
        """Returns the key/value metadata of this Blob."""
        return _frozendict(self._labels)

    def __eq__(self, o: Any) -> bool:
        return (
            (isinstance(o, Blob)) and
            (self.raw_bytes == o.raw_bytes) and
            (self.content_type == o.content_type) and
            (self.labels == o.labels)
        )

    def __repr__(self) -> str:
        params = [repr(self._raw_bytes)]
        if self._content_type is not None:
            params.append(f"content_type={self._content_type!r}")
        if self._labels:
            params.append("labels={}".format(json.dumps(self._labels, sort_keys=True)))
        params_string = ", ".join(params)
        return "Blob({})".format(params_string)
