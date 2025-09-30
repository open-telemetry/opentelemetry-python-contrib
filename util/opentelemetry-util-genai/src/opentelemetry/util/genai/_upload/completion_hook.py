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
from base64 import b64encode
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from functools import partial
from os import environ
from time import time
from typing import Any, Callable, Final, Literal, TextIO, cast
from uuid import uuid4

import fsspec

from opentelemetry._logs import LogRecord
from opentelemetry.semconv._incubating.attributes import gen_ai_attributes
from opentelemetry.trace import Span
from opentelemetry.util.genai import types
from opentelemetry.util.genai.completion_hook import CompletionHook
from opentelemetry.util.genai.environment_variables import (
    OTEL_INSTRUMENTATION_GENAI_UPLOAD_FORMAT,
)

GEN_AI_INPUT_MESSAGES_REF: Final = (
    gen_ai_attributes.GEN_AI_INPUT_MESSAGES + "_ref"
)
GEN_AI_OUTPUT_MESSAGES_REF: Final = (
    gen_ai_attributes.GEN_AI_OUTPUT_MESSAGES + "_ref"
)
GEN_AI_SYSTEM_INSTRUCTIONS_REF: Final = (
    gen_ai_attributes.GEN_AI_SYSTEM_INSTRUCTIONS + "_ref"
)

_MESSAGE_INDEX_KEY = "index"

Format = Literal["json", "jsonl"]
_FORMATS: tuple[Format, ...] = ("json", "jsonl")

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


class UploadCompletionHook(CompletionHook):
    """An completion hook using ``fsspec`` to upload to external storage

    This function can be used as the
    :func:`~opentelemetry.util.genai.completion_hook.load_completion_hook` implementation by
    setting :envvar:`OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK` to ``upload``.
    :envvar:`OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH` must be configured to specify the
    base path for uploads.

    Both the ``fsspec`` and ``opentelemetry-sdk`` packages should be installed, or a no-op
    implementation will be used instead. You can use ``opentelemetry-util-genai[upload]``
    as a requirement to achieve this.
    """

    def __init__(
        self,
        *,
        base_path: str,
        max_size: int = 20,
        upload_format: Format | None = None,
    ) -> None:
        self._base_path = base_path
        self._max_size = max_size

        if upload_format not in _FORMATS + (None,):
            raise ValueError(
                f"Invalid {upload_format=}. Must be one of {_FORMATS}"
            )

        if upload_format is None:
            environ_format = environ.get(
                OTEL_INSTRUMENTATION_GENAI_UPLOAD_FORMAT, "json"
            ).lower()
            if environ_format not in _FORMATS:
                upload_format = "json"
            else:
                upload_format = environ_format

        self._format: Final[Literal["json", "jsonl"]] = upload_format

        # Use a ThreadPoolExecutor for its queueing and thread management. The semaphore
        # limits the number of queued tasks. If the queue is full, data will be dropped.
        self._executor = ThreadPoolExecutor(max_workers=max_size)
        self._semaphore = threading.BoundedSemaphore(max_size)

    def _submit_all(self, upload_data: UploadData) -> None:
        def done(future: Future[None]) -> None:
            try:
                future.result()
            except Exception:  # pylint: disable=broad-except
                _logger.exception("uploader failed")
            finally:
                self._semaphore.release()

        for path, json_encodeable in upload_data.items():
            # could not acquire, drop data
            if not self._semaphore.acquire(blocking=False):  # pylint: disable=consider-using-with
                _logger.warning(
                    "upload queue is full, dropping upload %s",
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
                    "attempting to upload file after UploadCompletionHook.shutdown() was already called"
                )
                self._semaphore.release()

    def _calculate_ref_path(self) -> CompletionRefs:
        # TODO: experimental with using the trace_id and span_id, or fetching
        # gen_ai.response.id from the active span.

        uuid_str = str(uuid4())
        return CompletionRefs(
            inputs_ref=posixpath.join(
                self._base_path, f"{uuid_str}_inputs.{self._format}"
            ),
            outputs_ref=posixpath.join(
                self._base_path, f"{uuid_str}_outputs.{self._format}"
            ),
            system_instruction_ref=posixpath.join(
                self._base_path,
                f"{uuid_str}_system_instruction.{self._format}",
            ),
        )

    def _do_upload(
        self, path: str, json_encodeable: Callable[[], JsonEncodeable]
    ) -> None:
        if self._format == "json":
            # output as a single line with the json messages array
            message_lines = [json_encodeable()]
        else:
            # output as one line per message in the array
            message_lines = json_encodeable()
            # add an index for streaming readers of jsonl
            for message_idx, line in enumerate(message_lines):
                line[_MESSAGE_INDEX_KEY] = message_idx

        with fsspec_open(path, "w") as file:
            for message in message_lines:
                json.dump(
                    message,
                    file,
                    separators=(",", ":"),
                    cls=Base64JsonEncoder,
                )
                file.write("\n")

    def on_completion(
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

    def shutdown(self, *, timeout_sec: float = 10.0) -> None:
        deadline = time() + timeout_sec

        # Wait for all tasks to finish to flush the queue
        with ExitStack() as stack:
            for _ in range(self._max_size):
                remaining = deadline - time()
                if not self._semaphore.acquire(timeout=remaining):  # pylint: disable=consider-using-with
                    # Couldn't finish flushing all uploads before timeout
                    break

                stack.callback(self._semaphore.release)

            # Queue is flushed and blocked, start shutdown
            self._executor.shutdown(wait=False)


class Base64JsonEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if isinstance(o, bytes):
            return b64encode(o).decode()
        return super().default(o)
