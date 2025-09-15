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

import logging
import queue
import threading
from dataclasses import dataclass
from typing import Any

from opentelemetry._logs import LogRecord
from opentelemetry.trace import Span
from opentelemetry.util._once import Once
from opentelemetry.util.genai import types
from opentelemetry.util.genai.upload_hook import UploadHook, _NoOpUploadHook

_logger = logging.getLogger(__name__)


# If the SDK is available, use the BatchProcessor shared class for queueing, otherwise the hook will be a
# no-op.
try:
    import fsspec
except ImportError:
    fsspec = None


@dataclass
class Completion:
    inputs: list[types.InputMessage]
    outputs: list[types.OutputMessage]
    system_instruction: list[types.MessagePart]


if fsspec is not None:

    class FsspecCompletionExporter:
        """Implements uploading GenAI completions to a generic backend using fsspec

        This class is used by the `BatchUploadHook` to export completions to an external
        storage.
        """

        def export(self, completion: Completion) -> None:
            """upload a completion with fsspec, may be called concurrently"""
            # TODO: implement fsspec upload

    class FsspecUploadHook(UploadHook):
        def __init__(
            self, exporter: FsspecCompletionExporter, maxsize: int = 20
        ) -> None:
            self._exporter = exporter

            # Use opinionated defaults to start, we can add environment variables later
            self._queue: queue.Queue[Completion | None] = queue.Queue(
                maxsize=maxsize
            )
            self._consumer_thread = threading.Thread(
                target=self._consumer, daemon=True
            )
            self._consumer_thread.start()
            self._shutdown_once = Once()

        def _consumer(self) -> None:
            shutdown = False
            while not (shutdown and self._queue.empty()):
                completion = self._queue.get()
                if completion is None:
                    shutdown = True
                    self._queue.task_done()
                    continue

                # TODO: submit to a thread pool
                self._exporter.export(completion)
                self._queue.task_done()

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
            try:
                self._queue.put(
                    Completion(
                        inputs=inputs,
                        outputs=outputs,
                        system_instruction=system_instruction,
                    ),
                    block=False,
                )
            except queue.Full:
                logging.warning(
                    "gen ai fsspec upload queue is full, dropping completion"
                )

        def shutdown(self, timeout_sec: float = 5) -> None:
            """Shuts down any worker threads"""

            def do_shutdown() -> None:
                # TODO: proper deadlines
                self._queue.put(None, timeout=timeout_sec)
                self._consumer_thread.join(timeout=timeout_sec)

            self._shutdown_once.do_once(do_shutdown)

    def fsspec_upload_hook() -> UploadHook:
        return FsspecUploadHook(FsspecCompletionExporter())
else:

    def fsspec_upload_hook() -> UploadHook:
        return _NoOpUploadHook()
