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

"""ClickHouse connection pool for Analytics API.

This module provides a thread-safe connection pool for ClickHouse.
Connections are borrowed from the pool for each request and returned
after use, allowing efficient sharing across concurrent requests.
"""

import atexit
import logging
import os
import queue
import threading
from contextlib import contextmanager
from typing import Any, Generator, Optional

from clickhouse_driver import Client
from clickhouse_driver.errors import Error as ClickHouseError

from opentelemetry.genai.analytics.config import ClickHouseConfig, settings

logger = logging.getLogger(__name__)

# Default pool size - can be overridden via environment variable
DEFAULT_POOL_SIZE = 10
POOL_SIZE = int(os.environ.get("GENAI_ANALYTICS_POOL_SIZE", DEFAULT_POOL_SIZE))


class ClickHouseClient:
    """ClickHouse client wrapper for analytics queries.

    This wrapper manages the underlying clickhouse-driver Client instance
    and provides a consistent interface for query execution.
    """

    def __init__(self, config: Optional[ClickHouseConfig] = None):
        """Initialize ClickHouse client.

        Args:
            config: ClickHouse configuration. Uses global settings if not provided.
        """
        self.config = config or settings.clickhouse
        self._client: Optional[Client] = None

    def _parse_endpoint(self, endpoint: str) -> tuple[str, int]:
        """Parse tcp://host:port or host:port format."""
        endpoint = endpoint.replace("tcp://", "").replace("clickhouse://", "")
        if ":" in endpoint:
            host, port_str = endpoint.rsplit(":", 1)
            return host, int(port_str)
        return endpoint, 9000

    def _get_client(self) -> Client:
        """Get or create ClickHouse client."""
        if self._client is None:
            host, port = self._parse_endpoint(self.config.endpoint)
            self._client = Client(
                host=host,
                port=port,
                database=self.config.database,
                user=self.config.username,
                password=self.config.password,
                secure=self.config.secure,
                ca_certs=self.config.ca_cert,
                settings={
                    "use_numpy": False,
                },
            )
        return self._client

    def execute(
        self, query: str, params: Optional[dict[str, Any]] = None
    ) -> list[tuple]:
        """Execute a query and return results.

        Args:
            query: SQL query string.
            params: Query parameters.

        Returns:
            List of result tuples.
        """
        client = self._get_client()
        try:
            return client.execute(query, params or {})
        except ClickHouseError as e:
            logger.error("Query execution failed: %s", e)
            raise

    def execute_with_columns(
        self, query: str, params: Optional[dict[str, Any]] = None
    ) -> tuple[list[tuple], list[tuple[str, str]]]:
        """Execute a query and return results with column info.

        Args:
            query: SQL query string.
            params: Query parameters.

        Returns:
            Tuple of (results, column_info) where column_info is list of (name, type).
        """
        client = self._get_client()
        try:
            return client.execute(query, params or {}, with_column_types=True)
        except ClickHouseError as e:
            logger.error("Query execution failed: %s", e)
            raise

    def execute_iter(
        self, query: str, params: Optional[dict[str, Any]] = None
    ) -> Generator[tuple, None, None]:
        """Execute a query and yield results one at a time.

        Args:
            query: SQL query string.
            params: Query parameters.

        Yields:
            Result tuples.
        """
        client = self._get_client()
        try:
            yield from client.execute_iter(query, params or {})
        except ClickHouseError as e:
            logger.error("Query execution failed: %s", e)
            raise

    def ping(self) -> bool:
        """Check if connection is alive."""
        try:
            self.execute("SELECT 1")
            return True
        except ClickHouseError:
            return False

    def close(self) -> None:
        """Close the connection."""
        if self._client:
            self._client.disconnect()
            self._client = None


class ConnectionPool:
    """Thread-safe connection pool for ClickHouse clients.

    Manages a fixed-size pool of connections that are shared across
    threads. Connections are borrowed for use and returned to the pool
    when done.
    """

    def __init__(self, pool_size: int = POOL_SIZE):
        """Initialize the connection pool.

        Args:
            pool_size: Maximum number of connections in the pool.
        """
        self._pool_size = pool_size
        self._pool: queue.Queue[ClickHouseClient] = queue.Queue(maxsize=pool_size)
        self._all_clients: list[ClickHouseClient] = []
        self._lock = threading.Lock()
        self._initialized = False

    def _initialize_pool(self) -> None:
        """Lazily initialize the connection pool."""
        if self._initialized:
            return

        with self._lock:
            if self._initialized:
                return

            for _ in range(self._pool_size):
                client = ClickHouseClient()
                self._all_clients.append(client)
                self._pool.put(client)

            self._initialized = True
            logger.info("Initialized ClickHouse connection pool with %d connections", self._pool_size)

    def acquire(self, timeout: Optional[float] = 30.0) -> ClickHouseClient:
        """Acquire a connection from the pool.

        Args:
            timeout: Maximum time to wait for a connection (seconds).
                    None means wait forever.

        Returns:
            A ClickHouseClient instance.

        Raises:
            TimeoutError: If no connection is available within timeout.
        """
        self._initialize_pool()

        try:
            client = self._pool.get(timeout=timeout)
            return client
        except queue.Empty:
            raise TimeoutError(
                f"Could not acquire connection from pool within {timeout}s. "
                f"Pool size: {self._pool_size}. Consider increasing GENAI_ANALYTICS_POOL_SIZE."
            )

    def release(self, client: ClickHouseClient) -> None:
        """Return a connection to the pool.

        Args:
            client: The client to return to the pool.
        """
        try:
            self._pool.put_nowait(client)
        except queue.Full:
            # This shouldn't happen, but handle gracefully
            logger.warning("Connection pool is full, closing extra connection")
            client.close()

    def close_all(self) -> None:
        """Close all connections in the pool.

        Should be called during application shutdown.
        """
        with self._lock:
            for client in self._all_clients:
                try:
                    client.close()
                except Exception as e:
                    logger.warning("Error closing ClickHouse client: %s", e)
            self._all_clients.clear()
            self._initialized = False

            # Clear the queue
            while not self._pool.empty():
                try:
                    self._pool.get_nowait()
                except queue.Empty:
                    break

        logger.info("Closed all ClickHouse connections")

    def ping(self) -> bool:
        """Check if a connection from the pool is alive."""
        try:
            client = self.acquire(timeout=5.0)
            try:
                return client.ping()
            finally:
                self.release(client)
        except TimeoutError:
            return False


class PooledClient:
    """A context-managed client that auto-releases back to pool.

    This wrapper ensures the connection is always returned to the pool,
    even if an exception occurs.
    """

    def __init__(self, pool: ConnectionPool):
        self._pool = pool
        self._client: Optional[ClickHouseClient] = None

    def __enter__(self) -> ClickHouseClient:
        self._client = self._pool.acquire()
        return self._client

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._client is not None:
            self._pool.release(self._client)
            self._client = None


# Global connection pool
_connection_pool = ConnectionPool()

# Register cleanup on interpreter shutdown
atexit.register(_connection_pool.close_all)


def get_client() -> ClickHouseClient:
    """Get a client from the connection pool.

    WARNING: When using this function directly, you MUST return the client
    to the pool by calling release_client() when done. Prefer using
    get_connection() context manager instead.

    Returns:
        ClickHouseClient instance from the pool.
    """
    return _connection_pool.acquire()


def release_client(client: ClickHouseClient) -> None:
    """Return a client to the connection pool.

    Args:
        client: The client to return.
    """
    _connection_pool.release(client)


@contextmanager
def get_connection() -> Generator[ClickHouseClient, None, None]:
    """Context manager for ClickHouse connections.

    Borrows a connection from the pool and automatically returns it
    when the context exits. This is the preferred way to use connections.

    Example:
        with get_connection() as client:
            results = client.execute("SELECT * FROM table")

    Yields:
        ClickHouseClient instance from the pool.
    """
    client = _connection_pool.acquire()
    try:
        yield client
    finally:
        _connection_pool.release(client)
