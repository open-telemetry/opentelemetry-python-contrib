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

import hashlib
import logging
import posixpath
import threading
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from functools import partial
from os import environ
from time import time
from typing import Any, Callable, Final, Literal
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
from opentelemetry.util.genai.utils import gen_ai_json_dump

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
    inputs: list[types.InputMessage] | None
    outputs: list[types.OutputMessage] | None
    system_instruction: list[types.MessagePart] | None


@dataclass
class CompletionRefs:
    inputs_ref: str
    outputs_ref: str
    system_instruction_ref: str


JsonEncodeable = list[dict[str, Any]]

# mapping of upload path and whether the contents were hashed to the filename to function computing upload data dict
UploadData = dict[tuple[str, bool], Callable[[], JsonEncodeable]]


def is_system_instructions_hashable(
    system_instruction: list[types.MessagePart] | None,
) -> bool:
    return bool(system_instruction) and all(
        isinstance(x, types.Text) for x in system_instruction
    )


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
        lru_cache_max_size: int = 1024,
    ) -> None:
        self._max_size = max_size
        self._fs, base_path = fsspec.url_to_fs(base_path)
        self._base_path = self._fs.unstrip_protocol(base_path)
        self.lru_dict: OrderedDict[str, bool] = OrderedDict()
        self.lru_cache_max_size = lru_cache_max_size

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

        for (
            path,
            contents_hashed_to_filename,
        ), json_encodeable in upload_data.items():
            if contents_hashed_to_filename and self._file_exists(path):
                continue
            # could not acquire, drop data
            if not self._semaphore.acquire(blocking=False):  # pylint: disable=consider-using-with
                _logger.warning(
                    "upload queue is full, dropping upload %s",
                    path,
                )
                continue

            try:
                fut = self._executor.submit(
                    self._do_upload,
                    path,
                    contents_hashed_to_filename,
                    json_encodeable,
                )
                fut.add_done_callback(done)
            except RuntimeError:
                _logger.info(
                    "attempting to upload file after UploadCompletionHook.shutdown() was already called"
                )
                self._semaphore.release()

    def _calculate_ref_path(
        self, system_instruction: list[types.MessagePart]
    ) -> CompletionRefs:
        # TODO: experimental with using the trace_id and span_id, or fetching
        # gen_ai.response.id from the active span.
        system_instruction_hash = None
        if is_system_instructions_hashable(system_instruction):
            # Get a hash of the text.
            system_instruction_hash = hashlib.sha256(
                "\n".join(x.content for x in system_instruction).encode(  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue, reportUnknownArgumentType]
                    "utf-8"
                ),
                usedforsecurity=False,
            ).hexdigest()
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
                f"{system_instruction_hash or uuid_str}_system_instruction.{self._format}",
            ),
        )

    def _file_exists(self, path: str) -> bool:
        if path in self.lru_dict:
            self.lru_dict.move_to_end(path)
            return True
        # https://filesystem-spec.readthedocs.io/en/latest/api.html#fsspec.spec.AbstractFileSystem.exists
        file_exists = self._fs.exists(path)
        # don't cache this because soon the file will exist..
        if not file_exists:
            return False
        self.lru_dict[path] = True
        if len(self.lru_dict) > self.lru_cache_max_size:
            self.lru_dict.popitem(last=False)
        return True

    def _do_upload(
        self,
        path: str,
        contents_hashed_to_filename: bool,
        json_encodeable: Callable[[], JsonEncodeable],
    ) -> None:
        if contents_hashed_to_filename and self._file_exists(path):
            return
        if self._format == "json":
            # output as a single line with the json messages array
            message_lines = [json_encodeable()]
        else:
            # output as one line per message in the array
            message_lines = json_encodeable()
            # add an index for streaming readers of jsonl
            for message_idx, line in enumerate(message_lines):
                line[_MESSAGE_INDEX_KEY] = message_idx

        content_type = (
            "application/json"
            if self._format == "json"
            else "application/jsonl"
        )

        with self._fs.open(path, "w", content_type=content_type) as file:
            for message in message_lines:
                gen_ai_json_dump(message, file)
                file.write("\n")

        if contents_hashed_to_filename:
            self.lru_dict[path] = True
            if len(self.lru_dict) > self.lru_cache_max_size:
                self.lru_dict.popitem(last=False)

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
        if not any([inputs, outputs, system_instruction]):
            return
        # An empty list will not be uploaded.
        completion = Completion(
            inputs=inputs or None,
            outputs=outputs or None,
            system_instruction=system_instruction or None,
        )
        # generate the paths to upload to
        ref_names = self._calculate_ref_path(system_instruction)

        def to_dict(
            dataclass_list: list[types.InputMessage]
            | list[types.OutputMessage]
            | list[types.MessagePart],
        ) -> JsonEncodeable:
            return [asdict(dc) for dc in dataclass_list]

        references = [
            (ref_name, ref, ref_attr, contents_hashed_to_filename)
            for ref_name, ref, ref_attr, contents_hashed_to_filename in [
                (
                    ref_names.inputs_ref,
                    completion.inputs,
                    GEN_AI_INPUT_MESSAGES_REF,
                    False,
                ),
                (
                    ref_names.outputs_ref,
                    completion.outputs,
                    GEN_AI_OUTPUT_MESSAGES_REF,
                    False,
                ),
                (
                    ref_names.system_instruction_ref,
                    completion.system_instruction,
                    GEN_AI_SYSTEM_INSTRUCTIONS_REF,
                    is_system_instructions_hashable(
                        completion.system_instruction
                    ),
                ),
            ]
            if ref  # Filter out empty input/output/sys instruction
        ]
        self._submit_all(
            {
                (ref_name, contents_hashed_to_filename): partial(to_dict, ref)
                for ref_name, ref, _, contents_hashed_to_filename in references
            }
        )

        # stamp the refs on telemetry
        references = {ref_attr: name for name, _, ref_attr, _ in references}
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
