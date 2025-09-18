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

import json
import logging
import posixpath
import threading
from collections.abc import Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass
from functools import partial
from typing import Any, Callable, Final, Literal, TextIO, cast
from uuid import uuid4

import fsspec

from opentelemetry._logs import LogRecord
from opentelemetry.semconv._incubating.attributes import gen_ai_attributes
from opentelemetry.trace import Span
from opentelemetry.util.genai import types
from opentelemetry.util.genai.upload_hook import UploadHook

GEN_AI_INPUT_MESSAGES_REF: Final = (
    gen_ai_attributes.GEN_AI_INPUT_MESSAGES + "_ref"
)
GEN_AI_OUTPUT_MESSAGES_REF: Final = (
    gen_ai_attributes.GEN_AI_OUTPUT_MESSAGES + "_ref"
)
GEN_AI_SYSTEM_INSTRUCTIONS_REF: Final = (
    gen_ai_attributes.GEN_AI_SYSTEM_INSTRUCTIONS + "_ref"
)


_logger = logging.getLogger(__name__)


@dataclass
class Completion:
    inputs: list[types.InputMessage]
    outputs: list[types.OutputMessage]
    system_instruction: list[types.MessagePart]


@dataclass
class CompletionRefs:
    inputs_ref: str
    outputs_ref: str
    system_instruction_ref: str


JsonEncodeable = list[dict[str, Any]]

# mapping of upload path to function computing upload data dict
UploadData = dict[str, Callable[[], JsonEncodeable]]


def fsspec_open(urlpath: str, mode: Literal["w"]) -> TextIO:
    """typed wrapper around `fsspec.open`"""
    return cast(TextIO, fsspec.open(urlpath, mode))  # pyright: ignore[reportUnknownMemberType]


class FsspecUploadHook(UploadHook):
    """An upload hook using ``fsspec`` to upload to external storage

    This function can be used as the
    :func:`~opentelemetry.util.genai.upload_hook.load_upload_hook` implementation by
    setting :envvar:`OTEL_INSTRUMENTATION_GENAI_UPLOAD_HOOK` to ``fsspec``.
    :envvar:`OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH` must be configured to specify the
    base path for uploads.

    Both the ``fsspec`` and ``opentelemetry-sdk`` packages should be installed, or a no-op
    implementation will be used instead. You can use ``opentelemetry-util-genai[fsspec]``
    as a requirement to achieve this.
    """

    def __init__(
        self,
        *,
        base_path: str,
        max_size: int = 20,
    ) -> None:
        self._base_path = base_path
        self._max_size = max_size

        # Use a ThreadPoolExecutor for its queueing and thread management. The semaphore
        # limits the number of queued tasks. If the queue is full, data will be dropped.
        self._executor = ThreadPoolExecutor(max_workers=max_size)
        self._semaphore = threading.BoundedSemaphore(max_size)

    def _submit_all(self, upload_data: UploadData) -> None:
        def done(future: Future[None]) -> None:
            self._semaphore.release()

            try:
                future.result()
            except Exception:  # pylint: disable=broad-except
                _logger.exception("fsspec uploader failed")

        for path, json_encodeable in upload_data.items():
            # could not acquire, drop data
            if not self._semaphore.acquire(blocking=False):  # pylint: disable=consider-using-with
                _logger.warning(
                    "fsspec upload queue is full, dropping upload %s",
                    path,
                )
                continue

            try:
                fut = self._executor.submit(
                    self._do_upload, path, json_encodeable
                )
                fut.add_done_callback(done)
            except RuntimeError:
                _logger.info(
                    "attempting to upload file after FsspecUploadHook.shutdown() was already called"
                )
                break

    def _calculate_ref_path(self) -> CompletionRefs:
        # TODO: experimental with using the trace_id and span_id, or fetching
        # gen_ai.response.id from the active span.

        uuid_str = str(uuid4())
        return CompletionRefs(
            inputs_ref=posixpath.join(
                self._base_path, f"{uuid_str}_inputs.json"
            ),
            outputs_ref=posixpath.join(
                self._base_path, f"{uuid_str}_outputs.json"
            ),
            system_instruction_ref=posixpath.join(
                self._base_path, f"{uuid_str}_system_instruction.json"
            ),
        )

    @staticmethod
    def _do_upload(
        path: str, json_encodeable: Callable[[], JsonEncodeable]
    ) -> None:
        with fsspec_open(path, "w") as file:
            json.dump(json_encodeable(), file, separators=(",", ":"))

    def upload(
        self,
        *,
        inputs: list[types.InputMessage],
        outputs: list[types.OutputMessage],
        system_instruction: list[types.MessagePart],
        span: Span | None = None,
        log_record: LogRecord | None = None,
        **kwargs: Any,
    ) -> None:
        completion = Completion(
            inputs=inputs,
            outputs=outputs,
            system_instruction=system_instruction,
        )
        # generate the paths to upload to
        ref_names = self._calculate_ref_path()

        def to_dict(
            dataclass_list: list[types.InputMessage]
            | list[types.OutputMessage]
            | list[types.MessagePart],
        ) -> JsonEncodeable:
            return [asdict(dc) for dc in dataclass_list]

        self._submit_all(
            {
                # Use partial to defer as much as possible to the background threads
                ref_names.inputs_ref: partial(to_dict, completion.inputs),
                ref_names.outputs_ref: partial(to_dict, completion.outputs),
                ref_names.system_instruction_ref: partial(
                    to_dict, completion.system_instruction
                ),
            },
        )

        # stamp the refs on telemetry
        references = {
            GEN_AI_INPUT_MESSAGES_REF: ref_names.inputs_ref,
            GEN_AI_OUTPUT_MESSAGES_REF: ref_names.outputs_ref,
            GEN_AI_SYSTEM_INSTRUCTIONS_REF: ref_names.system_instruction_ref,
        }
        if span:
            span.set_attributes(references)
        if log_record:
            log_record.attributes = {
                **(log_record.attributes or {}),
                **references,
            }

    def shutdown(self) -> None:
        # TODO: support timeout
        self._executor.shutdown()
