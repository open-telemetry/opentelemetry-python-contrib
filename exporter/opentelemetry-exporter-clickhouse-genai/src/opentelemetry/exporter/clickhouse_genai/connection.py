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

"""ClickHouse connection manager for GenAI exporter."""

import logging
from typing import Any, Optional

from clickhouse_driver import Client
from clickhouse_driver.errors import Error as ClickHouseError

from opentelemetry.exporter.clickhouse_genai.config import (
    ClickHouseGenAIConfig,
)
from opentelemetry.exporter.clickhouse_genai.schema import (
    CREATE_DATABASE_SQL,
    LOGS_TABLE_SQL,
    METRICS_TABLE_SQL,
    TRACES_TABLE_SQL,
)

logger = logging.getLogger(__name__)


class ClickHouseConnection:
    """Manages ClickHouse native TCP connections with retry and batching."""

    def __init__(self, config: ClickHouseGenAIConfig):
        """Initialize ClickHouse connection.

        Args:
            config: ClickHouse configuration.
        """
        self.config = config
        self._client: Optional[Client] = None

    @property
    def client(self) -> Client:
        """Get or create ClickHouse client."""
        if self._client is None:
            self._client = self._create_client()
        return self._client

    def _create_client(self) -> Client:
        """Create ClickHouse native TCP client."""
        host, port = self._parse_endpoint(self.config.endpoint)

        compression = self.config.compression
        if compression == "none" or compression == "":
            compression = False

        return Client(
            host=host,
            port=port,
            database=self.config.database,
            user=self.config.username,
            password=self.config.password,
            secure=self.config.secure,
            ca_certs=self.config.ca_cert,
            compression=compression if compression else False,
            settings={
                "use_numpy": False,
                "insert_block_size": self.config.batch_size,
            },
        )

    def _parse_endpoint(self, endpoint: str) -> tuple:
        """Parse tcp://host:port or host:port format.

        Args:
            endpoint: ClickHouse endpoint string.

        Returns:
            Tuple of (host, port).
        """
        # Remove protocol prefix if present
        endpoint = endpoint.replace("tcp://", "").replace("clickhouse://", "")

        if ":" in endpoint:
            host, port_str = endpoint.rsplit(":", 1)
            return host, int(port_str)
        return endpoint, 9000  # Default native port

    def ensure_database(self) -> None:
        """Create database if it doesn't exist."""
        # Need to connect without database first
        host, port = self._parse_endpoint(self.config.endpoint)
        temp_client = Client(
            host=host,
            port=port,
            user=self.config.username,
            password=self.config.password,
            secure=self.config.secure,
            ca_certs=self.config.ca_cert,
        )
        try:
            temp_client.execute(
                CREATE_DATABASE_SQL.format(database=self.config.database)
            )
            logger.info("Database %s ensured", self.config.database)
        finally:
            temp_client.disconnect()

    def create_traces_table(self) -> None:
        """Create traces table with TTL and indexes."""
        sql = TRACES_TABLE_SQL.format(
            database=self.config.database,
            table=self.config.traces_table,
            ttl_days=self.config.ttl_days,
        )
        try:
            self.client.execute(sql)
            logger.info(
                "Traces table %s.%s created",
                self.config.database,
                self.config.traces_table,
            )
        except ClickHouseError as e:
            logger.error("Failed to create traces table: %s", e)
            raise

    def create_metrics_table(self) -> None:
        """Create metrics table."""
        sql = METRICS_TABLE_SQL.format(
            database=self.config.database,
            table=self.config.metrics_table,
            ttl_days=self.config.ttl_days,
        )
        try:
            self.client.execute(sql)
            logger.info(
                "Metrics table %s.%s created",
                self.config.database,
                self.config.metrics_table,
            )
        except ClickHouseError as e:
            logger.error("Failed to create metrics table: %s", e)
            raise

    def create_logs_table(self) -> None:
        """Create logs table."""
        sql = LOGS_TABLE_SQL.format(
            database=self.config.database,
            table=self.config.logs_table,
            ttl_days=self.config.ttl_days,
        )
        try:
            self.client.execute(sql)
            logger.info(
                "Logs table %s.%s created",
                self.config.database,
                self.config.logs_table,
            )
        except ClickHouseError as e:
            logger.error("Failed to create logs table: %s", e)
            raise

    def insert_traces(self, rows: list[dict[str, Any]]) -> None:
        """Batch insert trace rows using native protocol.

        Args:
            rows: List of trace row dictionaries.
        """
        if not rows:
            return

        try:
            self.client.execute(
                f"INSERT INTO {self.config.database}.{self.config.traces_table} VALUES",
                rows,
                types_check=True,
            )
            logger.info("Inserted %d trace rows", len(rows))
        except ClickHouseError as e:
            logger.error("Failed to insert traces: %s", e)
            raise

    def insert_metrics(self, rows: list[dict[str, Any]]) -> None:
        """Batch insert metric rows.

        Args:
            rows: List of metric row dictionaries.
        """
        if not rows:
            return

        try:
            self.client.execute(
                f"INSERT INTO {self.config.database}.{self.config.metrics_table} VALUES",
                rows,
                types_check=True,
            )
            logger.debug("Inserted %d metric rows", len(rows))
        except ClickHouseError as e:
            logger.error("Failed to insert metrics: %s", e)
            raise

    def insert_logs(self, rows: list[dict[str, Any]]) -> None:
        """Batch insert log rows.

        Args:
            rows: List of log row dictionaries.
        """
        if not rows:
            return

        try:
            self.client.execute(
                f"INSERT INTO {self.config.database}.{self.config.logs_table} VALUES",
                rows,
                types_check=True,
            )
            logger.debug("Inserted %d log rows", len(rows))
        except ClickHouseError as e:
            logger.error("Failed to insert logs: %s", e)
            raise

    def close(self) -> None:
        """Close the connection."""
        if self._client:
            self._client.disconnect()
            self._client = None
            logger.debug("ClickHouse connection closed")

    def ping(self) -> bool:
        """Check if connection is alive.

        Returns:
            True if connection is alive, False otherwise.
        """
        try:
            self.client.execute("SELECT 1")
            return True
        except ClickHouseError:
            return False
