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

"""ClickHouse connection manager for GenAI exporter.

Manages connections and provides insert methods for all tables:
- genai_spans: LLM/AI interactions
- spans: General purpose spans (db, http, messaging, rpc)
- genai_tool_calls: Tool/function executions
- genai_retrievals: RAG/vector DB queries
- genai_sessions: Session tracking
- genai_messages: Message-level tracking
- genai_metrics: Metrics
"""

import logging
from typing import Any, Optional

from clickhouse_driver import Client
from clickhouse_driver.errors import Error as ClickHouseError

from opentelemetry.exporter.clickhouse_genai.config import (
    ClickHouseGenAIConfig,
)
from opentelemetry.exporter.clickhouse_genai.schema import (
    CREATE_DATABASE_SQL,
    # Table name constants
    GENAI_SPANS_TABLE,
    GENAI_SPANS_TABLE_SQL,
    MESSAGES_TABLE,
    MESSAGES_TABLE_SQL,
    METRICS_TABLE,
    METRICS_TABLE_SQL,
    RETRIEVALS_TABLE,
    RETRIEVALS_TABLE_SQL,
    SESSIONS_TABLE,
    SESSIONS_TABLE_SQL,
    SPANS_TABLE,
    SPANS_TABLE_SQL,
    TOOL_CALLS_TABLE,
    TOOL_CALLS_TABLE_SQL,
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

    def create_all_tables(self) -> None:
        """Create all tables required for the new schema."""
        self.create_genai_spans_table()
        self.create_spans_table()
        self.create_tool_calls_table()
        self.create_retrievals_table()
        self.create_sessions_table()
        self.create_messages_table()
        self.create_metrics_table()

    def create_genai_spans_table(self) -> None:
        """Create genai_spans table for LLM interactions."""
        sql = GENAI_SPANS_TABLE_SQL.format(
            database=self.config.database,
            table=GENAI_SPANS_TABLE,
            ttl_days=self.config.ttl_days,
        )
        self._execute_create_table(sql, GENAI_SPANS_TABLE)

    def create_spans_table(self) -> None:
        """Create spans table for general purpose spans."""
        sql = SPANS_TABLE_SQL.format(
            database=self.config.database,
            table=SPANS_TABLE,
            ttl_days=self.config.ttl_days,
        )
        self._execute_create_table(sql, SPANS_TABLE)

    def create_tool_calls_table(self) -> None:
        """Create genai_tool_calls table."""
        sql = TOOL_CALLS_TABLE_SQL.format(
            database=self.config.database,
            table=TOOL_CALLS_TABLE,
            ttl_days=self.config.ttl_days,
        )
        self._execute_create_table(sql, TOOL_CALLS_TABLE)

    def create_retrievals_table(self) -> None:
        """Create genai_retrievals table."""
        sql = RETRIEVALS_TABLE_SQL.format(
            database=self.config.database,
            table=RETRIEVALS_TABLE,
            ttl_days=self.config.ttl_days,
        )
        self._execute_create_table(sql, RETRIEVALS_TABLE)

    def create_sessions_table(self) -> None:
        """Create genai_sessions table."""
        sql = SESSIONS_TABLE_SQL.format(
            database=self.config.database,
            table=SESSIONS_TABLE,
            ttl_days=self.config.ttl_days,
        )
        self._execute_create_table(sql, SESSIONS_TABLE)

    def create_messages_table(self) -> None:
        """Create genai_messages table."""
        sql = MESSAGES_TABLE_SQL.format(
            database=self.config.database,
            table=MESSAGES_TABLE,
            ttl_days=self.config.ttl_days,
        )
        self._execute_create_table(sql, MESSAGES_TABLE)

    def create_metrics_table(self) -> None:
        """Create genai_metrics table."""
        sql = METRICS_TABLE_SQL.format(
            database=self.config.database,
            table=METRICS_TABLE,
            ttl_days=self.config.ttl_days,
        )
        self._execute_create_table(sql, METRICS_TABLE)

    def _execute_create_table(self, sql: str, table_name: str) -> None:
        """Execute create table SQL with error handling."""
        try:
            self.client.execute(sql)
            logger.info(
                "Table %s.%s created/verified",
                self.config.database,
                table_name,
            )
        except ClickHouseError as e:
            logger.error("Failed to create table %s: %s", table_name, e)
            raise

    # =========================================================================
    # INSERT METHODS
    # =========================================================================

    def insert_genai_spans(self, rows: list[dict[str, Any]]) -> None:
        """Batch insert genai_spans rows.

        Args:
            rows: List of genai span row dictionaries.
        """
        self._insert_rows(GENAI_SPANS_TABLE, rows, "genai_spans")

    def insert_spans(self, rows: list[dict[str, Any]]) -> None:
        """Batch insert spans rows (general purpose spans).

        Args:
            rows: List of span row dictionaries.
        """
        self._insert_rows(SPANS_TABLE, rows, "spans")

    def insert_tool_calls(self, rows: list[dict[str, Any]]) -> None:
        """Batch insert tool_calls rows.

        Args:
            rows: List of tool call row dictionaries.
        """
        self._insert_rows(TOOL_CALLS_TABLE, rows, "tool_calls")

    def insert_retrievals(self, rows: list[dict[str, Any]]) -> None:
        """Batch insert retrievals rows.

        Args:
            rows: List of retrieval row dictionaries.
        """
        self._insert_rows(RETRIEVALS_TABLE, rows, "retrievals")

    def insert_sessions(self, rows: list[dict[str, Any]]) -> None:
        """Batch insert/update sessions rows.

        Note: genai_sessions uses ReplacingMergeTree, so inserts
        with the same SessionId will eventually merge (deduplicate).

        Args:
            rows: List of session row dictionaries.
        """
        self._insert_rows(SESSIONS_TABLE, rows, "sessions")

    def insert_messages(self, rows: list[dict[str, Any]]) -> None:
        """Batch insert messages rows.

        Args:
            rows: List of message row dictionaries.
        """
        self._insert_rows(MESSAGES_TABLE, rows, "messages")

    def insert_metrics(self, rows: list[dict[str, Any]]) -> None:
        """Batch insert metric rows.

        Args:
            rows: List of metric row dictionaries.
        """
        self._insert_rows(METRICS_TABLE, rows, "metrics")

    def _insert_rows(
        self, table: str, rows: list[dict[str, Any]], log_name: str
    ) -> None:
        """Generic row insertion with error handling.

        Args:
            table: Table name.
            rows: List of row dictionaries.
            log_name: Name for logging purposes.
        """
        if not rows:
            return

        try:
            # Log the first row's keys for debugging
            if rows:
                logger.debug("Inserting into %s with columns: %s", table, list(rows[0].keys()))
            self.client.execute(
                f"INSERT INTO {self.config.database}.{table} VALUES",
                rows,
                types_check=True,
            )
            logger.debug("Inserted %d %s rows", len(rows), log_name)
        except Exception as e:
            logger.error("Failed to insert %s: %s", log_name, e)
            raise

    # =========================================================================
    # LEGACY METHODS (for backward compatibility)
    # =========================================================================

    def create_traces_table(self) -> None:
        """Create traces table (legacy alias for genai_spans)."""
        self.create_genai_spans_table()

    def create_logs_table(self) -> None:
        """Create logs table (legacy alias for messages)."""
        self.create_messages_table()

    def insert_traces(self, rows: list[dict[str, Any]]) -> None:
        """Insert traces (legacy alias for genai_spans)."""
        self.insert_genai_spans(rows)

    def insert_logs(self, rows: list[dict[str, Any]]) -> None:
        """Insert logs (legacy alias for messages)."""
        self.insert_messages(rows)

    # =========================================================================
    # CONNECTION MANAGEMENT
    # =========================================================================

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
