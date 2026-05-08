# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from typing import Optional, Union

import google.genai.types as genai_types


def create_response(
    part: Optional[genai_types.Part] = None,
    parts: Optional[list[genai_types.Part]] = None,
    content: Optional[genai_types.Content] = None,
    candidate: Optional[genai_types.Candidate] = None,
    candidates: Optional[list[genai_types.Candidate]] = None,
    text: Optional[str] = None,
    input_tokens: Optional[int] = None,
    thinking_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    cached_tokens: Optional[int] = None,
    model_version: Optional[str] = None,
    usage_metadata: Optional[
        genai_types.GenerateContentResponseUsageMetadata
    ] = None,
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
    if cached_tokens is not None:
        usage_metadata.cached_content_token_count = cached_tokens
    if thinking_tokens is not None:
        usage_metadata.thoughts_token_count = thinking_tokens
    return genai_types.GenerateContentResponse(
        candidates=candidates,
        usage_metadata=usage_metadata,
        model_version=model_version,
        **kwargs,
    )


def convert_to_response(
    arg: Union[str, genai_types.GenerateContentResponse, dict],
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
