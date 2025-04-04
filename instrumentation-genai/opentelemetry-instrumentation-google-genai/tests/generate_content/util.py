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

from __future__ import annotations

import google.genai.types as genai_types


def create_response(
    part: genai_types.Part | None = None,
    parts: list[genai_types.Part] | None = None,
    content: genai_types.Content | None = None,
    candidate: genai_types.Candidate | None = None,
    candidates: list[genai_types.Candidate] | None = None,
    text: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    model_version: str | None = None,
    usage_metadata: genai_types.GenerateContentResponseUsageMetadata
    | None = None,
    **kwargs,
) -> genai_types.GenerateContentResponse:
    # Build up the "candidates" subfield
    if text is None:
        text = "Some response text"
    if part is None:
        part = genai_types.Part(text=text)
    if parts is None:
        parts = [part]
    if content is None:
        content = genai_types.Content(parts=parts, role="model")
    if candidate is None:
        candidate = genai_types.Candidate(content=content)
    if candidates is None:
        candidates = [candidate]

    # Build up the "usage_metadata" subfield
    if usage_metadata is None:
        usage_metadata = genai_types.GenerateContentResponseUsageMetadata()
    if input_tokens is not None:
        usage_metadata.prompt_token_count = input_tokens
    if output_tokens is not None:
        usage_metadata.candidates_token_count = output_tokens
    return genai_types.GenerateContentResponse(
        candidates=candidates,
        usage_metadata=usage_metadata,
        model_version=model_version,
        **kwargs,
    )


def convert_to_response(
    arg: str | genai_types.GenerateContentResponse | dict,
) -> genai_types.GenerateContentResponse:
    if isinstance(arg, str):
        return create_response(text=arg)
    if isinstance(arg, genai_types.GenerateContentResponse):
        return arg
    if isinstance(arg, dict):
        return create_response(**arg)
    raise ValueError(
        f"Unsure how to convert {arg} of type {arg.__class__.__name__} to response."
    )
