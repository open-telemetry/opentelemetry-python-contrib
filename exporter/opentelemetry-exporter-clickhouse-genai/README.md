# OpenTelemetry ClickHouse GenAI Exporter

This package provides exporters for sending OpenTelemetry traces, metrics, and logs to ClickHouse, with schemas specifically optimized for GenAI/LLM observability.

## Features

- **Maximally columnar schema** - Dedicated columns for all GenAI attributes (tokens, models, operations) for fast analytics
- **Comprehensive indexing** - Bloom filters, MinMax, Set indexes, and NGram for text search
- **Native TCP protocol** - Uses `clickhouse-driver` for best insert performance
- **Auto-schema creation** - Tables created automatically on startup (can be disabled)
- **Configurable TTL** - Data retention with automatic cleanup
- **OTLP Collector mode** - Run as a standalone service with gRPC/HTTP receivers

## Installation

```bash
pip install opentelemetry-exporter-clickhouse-genai
```

## Quick Start

### Traces

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.clickhouse_genai import (
    ClickHouseGenAISpanExporter,
    ClickHouseGenAIConfig,
)

config = ClickHouseGenAIConfig(
    endpoint="localhost:9000",
    database="otel_genai",
    ttl_days=7,
)

exporter = ClickHouseGenAISpanExporter(config)
provider = TracerProvider()
provider.add_span_processor(BatchSpanProcessor(exporter))
trace.set_tracer_provider(provider)
```

### Metrics

```python
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.clickhouse_genai import (
    ClickHouseGenAIMetricsExporter,
    ClickHouseGenAIConfig,
)

config = ClickHouseGenAIConfig(endpoint="localhost:9000")
exporter = ClickHouseGenAIMetricsExporter(config)
reader = PeriodicExportingMetricReader(exporter)
provider = MeterProvider(metric_readers=[reader])
metrics.set_meter_provider(provider)
```

### Logs

```python
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.clickhouse_genai import (
    ClickHouseGenAILogsExporter,
    ClickHouseGenAIConfig,
)

config = ClickHouseGenAIConfig(endpoint="localhost:9000")
exporter = ClickHouseGenAILogsExporter(config)
provider = LoggerProvider()
provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
```

### OTLP Collector Mode

Run as a standalone OTLP collector that receives telemetry via gRPC/HTTP and exports to ClickHouse:

```python
from opentelemetry.exporter.clickhouse_genai import (
    OTLPClickHouseCollector,
    CollectorConfig,
)

config = CollectorConfig(
    grpc_endpoint="0.0.0.0:4317",
    http_endpoint="0.0.0.0:4318",
    endpoint="localhost:9000",
    database="otel_genai",
)

collector = OTLPClickHouseCollector(config)
collector.start()
# Collector is now running, accepting OTLP data on ports 4317 (gRPC) and 4318 (HTTP)
# Press Ctrl+C or call collector.stop() to shutdown
```

Or via CLI:

```bash
otel-clickhouse-collector \
  --grpc-endpoint 0.0.0.0:4317 \
  --http-endpoint 0.0.0.0:4318 \
  --clickhouse-endpoint localhost:9000 \
  --clickhouse-database otel_genai \
  -v
```

## Running with Docker Compose

The easiest way to run the collector with ClickHouse:

```bash
# Start ClickHouse and the collector
docker-compose up -d

# View collector logs
docker-compose logs -f collector

# Stop all services
docker-compose down
```

This starts:
- **ClickHouse** on ports 8123 (HTTP) and 9000 (native)
- **OTLP Collector** on ports 4317 (gRPC) and 4318 (HTTP)

### Send Test Data

```bash
# Send traces via HTTP
curl -X POST http://localhost:4318/v1/traces \
  -H "Content-Type: application/json" \
  -d '{"resourceSpans":[]}'

# Query data in ClickHouse
docker-compose exec clickhouse clickhouse-client \
  -q "SELECT * FROM otel_genai.genai_traces LIMIT 10"
```

### Configure Your Application

Point your OTLP exporter to the collector:

```python
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# Export to the collector via gRPC
exporter = OTLPSpanExporter(endpoint="localhost:4317", insecure=True)
```

Or via environment variables:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OTEL_EXPORTER_CLICKHOUSE_ENDPOINT` | `localhost:9000` | ClickHouse endpoint |
| `OTEL_EXPORTER_CLICKHOUSE_DATABASE` | `otel_genai` | Database name |
| `OTEL_EXPORTER_CLICKHOUSE_USERNAME` | `default` | Username |
| `OTEL_EXPORTER_CLICKHOUSE_PASSWORD` | `` | Password |
| `OTEL_EXPORTER_CLICKHOUSE_SECURE` | `false` | Use TLS |
| `OTEL_EXPORTER_CLICKHOUSE_CREATE_SCHEMA` | `true` | Auto-create tables |
| `OTEL_EXPORTER_CLICKHOUSE_TTL_DAYS` | `7` | Data retention days |
| `OTEL_EXPORTER_CLICKHOUSE_BATCH_SIZE` | `1000` | Insert batch size |
| `OTEL_EXPORTER_CLICKHOUSE_COMPRESSION` | `lz4` | Compression (lz4, zstd, none) |
| `OTEL_COLLECTOR_GRPC_ENDPOINT` | `0.0.0.0:4317` | gRPC receiver endpoint |
| `OTEL_COLLECTOR_HTTP_ENDPOINT` | `0.0.0.0:4318` | HTTP receiver endpoint |
| `OTEL_COLLECTOR_ENABLE_GRPC` | `true` | Enable gRPC receiver |
| `OTEL_COLLECTOR_ENABLE_HTTP` | `true` | Enable HTTP receiver |
| `OTEL_COLLECTOR_BATCH_TIMEOUT_MS` | `5000` | Batch flush timeout (ms) |
| `OTEL_COLLECTOR_MAX_QUEUE_SIZE` | `10000` | Max items in queue |

### Programmatic Configuration

```python
from opentelemetry.exporter.clickhouse_genai import ClickHouseGenAIConfig

config = ClickHouseGenAIConfig(
    endpoint="clickhouse.example.com:9000",
    database="prod_genai",
    username="otel_user",
    password="secret",
    secure=True,
    ca_cert="/path/to/ca.crt",
    create_schema=False,  # Manage schema manually
    ttl_days=30,
    compression="zstd",
)
```

## Schema

The exporter creates three tables optimized for GenAI observability:

### `genai_traces`

Stores span data with dedicated columns for:
- GenAI operation details (operation name, system, model)
- Token usage (input, output, cached, reasoning tokens)
- Request parameters (temperature, top_p, max_tokens)
- Tool/function calling information
- Request/response content (when capture mode is ALL)

### `genai_metrics`

Stores metrics with columns for:
- Duration histograms
- Token usage histograms
- GenAI dimensions for filtering

### `genai_logs`

Stores log events with columns for:
- Message content by role (user, assistant, system, tool)
- Choice information with finish reasons
- Tool call details

## Example Queries

```sql
-- Token usage by model
SELECT
    GenAiRequestModel,
    sum(InputTokens) AS total_input,
    sum(OutputTokens) AS total_output
FROM genai_traces
WHERE Timestamp >= now() - INTERVAL 1 DAY
GROUP BY GenAiRequestModel;

-- Latency percentiles
SELECT
    GenAiOperationName,
    GenAiRequestModel,
    quantile(0.50)(DurationNs / 1000000) AS p50_ms,
    quantile(0.95)(DurationNs / 1000000) AS p95_ms
FROM genai_traces
WHERE Timestamp >= now() - INTERVAL 1 HOUR
GROUP BY GenAiOperationName, GenAiRequestModel;

-- Error rate by provider
SELECT
    GenAiSystem,
    countIf(HasError = 1) AS errors,
    count() AS total,
    round(errors / total * 100, 2) AS error_rate_pct
FROM genai_traces
WHERE Timestamp >= now() - INTERVAL 1 DAY
GROUP BY GenAiSystem;
```

## License

Apache License 2.0
