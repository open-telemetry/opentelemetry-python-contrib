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

"""Batch processor for OTLP Collector."""

import logging
import threading
from queue import Empty, Full, Queue
from typing import Any, Callable, List

logger = logging.getLogger(__name__)


class BatchProcessor:
    """Thread-safe batch processor for telemetry data.

    Batches incoming items and flushes to an export function when either:
    - The batch size threshold is reached
    - The timeout threshold is reached

    Handles backpressure by dropping items when the queue is full.
    """

    def __init__(
        self,
        export_fn: Callable[[List[Any]], None],
        batch_size: int = 1000,
        timeout_ms: int = 5000,
        max_queue_size: int = 10000,
    ):
        """Initialize the batch processor.

        Args:
            export_fn: Function to call with batched items.
            batch_size: Maximum items per batch before flush.
            timeout_ms: Maximum time (ms) before flush.
            max_queue_size: Maximum items in queue before dropping.
        """
        self._export_fn = export_fn
        self._batch_size = batch_size
        self._timeout_seconds = timeout_ms / 1000.0
        self._max_queue_size = max_queue_size

        self._queue: Queue = Queue(maxsize=max_queue_size)
        self._batch: List[Any] = []
        self._lock = threading.Lock()
        self._running = False
        self._worker_thread: threading.Thread | None = None
        self._shutdown_event = threading.Event()

        # Metrics
        self._items_received = 0
        self._items_exported = 0
        self._items_dropped = 0
        self._batches_exported = 0

    def start(self) -> None:
        """Start the batch processor worker thread."""
        if self._running:
            return

        self._running = True
        self._shutdown_event.clear()
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            name="BatchProcessor-Worker",
            daemon=True,
        )
        self._worker_thread.start()
        logger.info(
            "BatchProcessor started (batch_size=%d, timeout_ms=%d)",
            self._batch_size,
            int(self._timeout_seconds * 1000),
        )

    def stop(self, timeout: float = 10.0) -> None:
        """Stop the batch processor and flush remaining items.

        Args:
            timeout: Maximum time to wait for shutdown (seconds).
        """
        if not self._running:
            return

        self._running = False
        self._shutdown_event.set()

        if self._worker_thread:
            self._worker_thread.join(timeout=timeout)
            if self._worker_thread.is_alive():
                logger.warning("BatchProcessor worker did not stop in time")
            self._worker_thread = None

        # Final flush of any remaining items
        self._flush()
        logger.info(
            "BatchProcessor stopped (received=%d, exported=%d, dropped=%d)",
            self._items_received,
            self._items_exported,
            self._items_dropped,
        )

    def enqueue(self, items: List[Any]) -> int:
        """Add items to the processing queue.

        Args:
            items: List of items to process.

        Returns:
            Number of items successfully queued.
        """
        queued = 0
        for item in items:
            try:
                self._queue.put_nowait(item)
                queued += 1
                self._items_received += 1
            except Full:
                self._items_dropped += 1
                logger.warning(
                    "BatchProcessor queue full, dropped item (total dropped: %d)",
                    self._items_dropped,
                )

        return queued

    def _worker_loop(self) -> None:
        """Worker thread that batches and exports items."""
        while self._running or not self._queue.empty():
            try:
                # Wait for item with timeout
                item = self._queue.get(timeout=self._timeout_seconds)
                with self._lock:
                    self._batch.append(item)

                # Check if batch is full
                if len(self._batch) >= self._batch_size:
                    self._flush()

            except Empty:
                # Timeout reached, flush partial batch
                if self._batch:
                    self._flush()

            # Check for shutdown signal
            if self._shutdown_event.is_set() and self._queue.empty():
                break

    def _flush(self) -> None:
        """Flush current batch to exporter."""
        with self._lock:
            if not self._batch:
                return

            batch_to_export = self._batch
            self._batch = []

        try:
            self._export_fn(batch_to_export)
            self._items_exported += len(batch_to_export)
            self._batches_exported += 1
            logger.debug(
                "Flushed batch of %d items (total batches: %d)",
                len(batch_to_export),
                self._batches_exported,
            )
        except Exception as e:
            logger.error(
                "Failed to export batch of %d items: %s",
                len(batch_to_export),
                e,
            )
            # Items are lost on export failure
            # Could implement retry logic here if needed

    @property
    def stats(self) -> dict:
        """Get processor statistics.

        Returns:
            Dictionary with processor stats.
        """
        return {
            "items_received": self._items_received,
            "items_exported": self._items_exported,
            "items_dropped": self._items_dropped,
            "batches_exported": self._batches_exported,
            "queue_size": self._queue.qsize(),
            "pending_batch_size": len(self._batch),
        }
