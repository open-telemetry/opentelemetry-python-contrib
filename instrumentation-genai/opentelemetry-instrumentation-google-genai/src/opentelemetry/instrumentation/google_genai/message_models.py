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

# Copied and adapted from
# https://gist.github.com/lmolkova/09ba0de7f68280f1eac27a6acfd9b1a6?permalink_comment_id=5578799#gistcomment-5578799

from enum import Enum
from typing import Annotated, Literal

from pydantic import Base64Encoder, BaseModel, EncodedBytes


class Base64OneWayEncoder(Base64Encoder):
    @classmethod
    def decode(cls, data: bytes) -> bytes:
        """NoOp"""
        return data


Base64EncodedBytes = Annotated[
    bytes, EncodedBytes(encoder=Base64OneWayEncoder)
]


class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class BlobPart(BaseModel):
    type: Literal["blob"] = "blob"
    mime_type: str
    data: Base64EncodedBytes

    class Config:
        extra = "allow"


class FileDataPart(BaseModel):
    type: Literal["file_data"] = "file_data"
    mime_type: str
    file_uri: str

    class Config:
        extra = "allow"
