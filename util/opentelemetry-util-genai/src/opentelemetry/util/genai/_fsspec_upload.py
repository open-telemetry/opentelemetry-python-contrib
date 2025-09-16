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
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass
from functools import partial
from os import environ
from typing import Any, Callable, Literal, TextIO, cast
from uuid import uuid4

from opentelemetry._logs import LogRecord
from opentelemetry.trace import Span
from opentelemetry.util.genai import types
from opentelemetry.util.genai.environment_variables import (
    OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH,
)
from opentelemetry.util.genai.upload_hook import UploadHook, _NoOpUploadHook

# If fsspec is not installed the hook will be a no-op.
try:
    import fsspec
except ImportError:
    fsspec = None

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

if fsspec is not None:
    # save a copy for the type checker
    fsspec_copy = fsspec

    def fsspec_open(urlpath: str, mode: Literal["w"]) -> TextIO:
        """typed wrapper around `fsspec.open`"""
        return cast(TextIO, fsspec_copy.open(urlpath, mode))  # pyright: ignore[reportUnknownMemberType]

    class FsspecUploader:
        """Implements uploading GenAI completions to a generic backend using fsspec

        This class is used by the `BatchUploadHook` to upload completions to an external
        storage.
        """

        def upload(  # pylint: disable=no-self-use
            self,
            path: str,
            json_encodeable: Callable[[], JsonEncodeable],
        ) -> None:
            with fsspec_open(path, "w") as file:
                json.dump(json_encodeable(), file, separators=(",", ":"))

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
            uploader: FsspecUploader,
            base_path: str,
            max_size: int = 20,
        ) -> None:
            self._base_path = base_path
            self._uploader = uploader
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
                    return

                try:
                    fut = self._executor.submit(
                        self._uploader.upload, path, json_encodeable
                    )
                    fut.add_done_callback(done)
                except RuntimeError:
                    _logger.info(
                        "attempting to upload file after FsspecUploadHook.shutdown() was already called"
                    )
                    break

        def calculate_ref_path(self, completion: Completion) -> CompletionRefs:
            """Generate a path to the reference

            The default implementation uses :func:`~uuid.uuid4` to generate a random name per completion.
            """
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
            ref_names = self.calculate_ref_path(completion)

            def to_dict(
                dataclass_list: list[types.InputMessage]
                | list[types.OutputMessage]
                | list[types.MessagePart],
            ) -> list[dict[str, Any]]:
                return [asdict(dc) for dc in dataclass_list]

            self._submit_all(
                {
                    ref_names.inputs_ref: partial(to_dict, completion.inputs),
                    ref_names.outputs_ref: partial(
                        to_dict, completion.outputs
                    ),
                    ref_names.system_instruction_ref: partial(
                        to_dict, completion.system_instruction
                    ),
                },
            )

            # TODO: stamp the refs on telemetry

        def shutdown(self) -> None:
            # TODO: support timeout
            self._executor.shutdown()

    def fsspec_upload_hook() -> UploadHook:
        base_path = environ.get(OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH)
        if not base_path:
            return _NoOpUploadHook()

        return FsspecUploadHook(
            uploader=FsspecUploader(),
            base_path=base_path,
        )
else:

    def fsspec_upload_hook() -> UploadHook:
        return _NoOpUploadHook()
