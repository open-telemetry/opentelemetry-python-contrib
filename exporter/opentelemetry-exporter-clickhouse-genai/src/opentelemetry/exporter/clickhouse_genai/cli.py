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

"""CLI for OTLP ClickHouse Collector."""

import argparse
import logging
import signal
import sys
from typing import Optional

from opentelemetry.exporter.clickhouse_genai.collector import (
    OTLPClickHouseCollector,
)
from opentelemetry.exporter.clickhouse_genai.config import CollectorConfig


def setup_logging(verbose: bool = False) -> None:
    """Configure logging.

    Args:
        verbose: Whether to enable verbose logging.
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description="OTLP Collector with ClickHouse export for GenAI observability",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Receiver settings
    receiver_group = parser.add_argument_group("Receiver Settings")
    receiver_group.add_argument(
        "--grpc-endpoint",
        default="0.0.0.0:4317",
        help="gRPC receiver endpoint (host:port)",
    )
    receiver_group.add_argument(
        "--http-endpoint",
        default="0.0.0.0:4318",
        help="HTTP receiver endpoint (host:port)",
    )
    receiver_group.add_argument(
        "--disable-grpc",
        action="store_true",
        help="Disable gRPC receiver",
    )
    receiver_group.add_argument(
        "--disable-http",
        action="store_true",
        help="Disable HTTP receiver",
    )
    receiver_group.add_argument(
        "--grpc-max-workers",
        type=int,
        default=10,
        help="Maximum gRPC worker threads",
    )

    # ClickHouse settings
    ch_group = parser.add_argument_group("ClickHouse Settings")
    ch_group.add_argument(
        "--clickhouse-endpoint",
        default="localhost:9000",
        help="ClickHouse server endpoint (host:port)",
    )
    ch_group.add_argument(
        "--clickhouse-database",
        default="otel_genai",
        help="ClickHouse database name",
    )
    ch_group.add_argument(
        "--clickhouse-username",
        default="default",
        help="ClickHouse username",
    )
    ch_group.add_argument(
        "--clickhouse-password",
        default="",
        help="ClickHouse password",
    )
    ch_group.add_argument(
        "--clickhouse-secure",
        action="store_true",
        help="Use TLS for ClickHouse connection",
    )
    ch_group.add_argument(
        "--clickhouse-ca-cert",
        default=None,
        help="Path to CA certificate for ClickHouse TLS",
    )
    ch_group.add_argument(
        "--no-create-schema",
        action="store_true",
        help="Don't auto-create ClickHouse tables",
    )
    ch_group.add_argument(
        "--ttl-days",
        type=int,
        default=7,
        help="Data retention period in days",
    )
    ch_group.add_argument(
        "--compression",
        choices=["lz4", "zstd", "none"],
        default="lz4",
        help="ClickHouse compression algorithm",
    )

    # Batch settings
    batch_group = parser.add_argument_group("Batch Settings")
    batch_group.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Number of records per batch",
    )
    batch_group.add_argument(
        "--batch-timeout-ms",
        type=int,
        default=5000,
        help="Batch flush timeout in milliseconds",
    )
    batch_group.add_argument(
        "--max-queue-size",
        type=int,
        default=10000,
        help="Maximum items in processing queue",
    )

    # General settings
    general_group = parser.add_argument_group("General Settings")
    general_group.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    return parser.parse_args()


def main() -> int:
    """Main entry point.

    Returns:
        Exit code.
    """
    args = parse_args()
    setup_logging(verbose=args.verbose)

    logger = logging.getLogger(__name__)

    # Build configuration
    try:
        config = CollectorConfig(
            # Receiver settings
            grpc_endpoint=args.grpc_endpoint,
            http_endpoint=args.http_endpoint,
            enable_grpc=not args.disable_grpc,
            enable_http=not args.disable_http,
            grpc_max_workers=args.grpc_max_workers,
            # ClickHouse settings
            endpoint=args.clickhouse_endpoint,
            database=args.clickhouse_database,
            username=args.clickhouse_username,
            password=args.clickhouse_password,
            secure=args.clickhouse_secure,
            ca_cert=args.clickhouse_ca_cert,
            create_schema=not args.no_create_schema,
            ttl_days=args.ttl_days,
            compression=args.compression,
            # Batch settings
            batch_size=args.batch_size,
            batch_timeout_ms=args.batch_timeout_ms,
            max_queue_size=args.max_queue_size,
        )
    except ValueError as e:
        logger.error("Configuration error: %s", e)
        return 1

    # Create collector
    collector = OTLPClickHouseCollector(config)

    # Handle shutdown signals
    shutdown_event = False

    def shutdown_handler(signum: int, frame: Optional[object]) -> None:
        nonlocal shutdown_event
        if shutdown_event:
            logger.warning("Force shutdown requested")
            sys.exit(1)

        shutdown_event = True
        logger.info("Shutdown signal received, stopping collector...")
        collector.stop()

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    # Start collector
    try:
        collector.start()

        logger.info("Collector is running. Press Ctrl+C to stop.")
        logger.info(
            "Endpoints: gRPC=%s, HTTP=%s",
            config.grpc_endpoint if config.enable_grpc else "disabled",
            config.http_endpoint if config.enable_http else "disabled",
        )
        logger.info(
            "ClickHouse: %s/%s",
            config.endpoint,
            config.database,
        )

        # Block until terminated
        collector.wait_for_termination()

    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
        collector.stop()
    except Exception as e:
        logger.error("Collector error: %s", e)
        collector.stop()
        return 1

    logger.info("Collector shutdown complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
