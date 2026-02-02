# OpenTelemetry GenAI Analytics API

FastAPI-based analytics service for querying LLM observability data stored in ClickHouse.

## Features

- **Cost Analytics**: Track spending by provider, model, tenant, user
- **Token Usage**: Monitor input/output token consumption
- **Latency Tracking**: P50/P95/P99 percentiles by provider/model
- **Error Monitoring**: Error rates and breakdown by type
- **Model Usage**: Distribution and trends across models
- **User/Tenant Analytics**: Per-user and per-tenant metrics
- **Session Analytics**: Conversation metrics and outcomes
- **Tool Usage**: Function/tool invocation statistics
- **Provider Comparison**: Compare providers across all metrics
- **Audit Trail**: Full trace history with filtering

## Installation

```bash
pip install opentelemetry-genai-analytics-api
```

## Quick Start

### Running the Service

```bash
# Using the CLI command
genai-analytics-api

# Or using uvicorn directly
uvicorn opentelemetry.genai.analytics.main:app --host 0.0.0.0 --port 8080
```

### Configuration

The service uses environment variables for configuration:

```bash
# ClickHouse Connection (same as exporter)
OTEL_EXPORTER_CLICKHOUSE_ENDPOINT=localhost:9000
OTEL_EXPORTER_CLICKHOUSE_DATABASE=otel_genai
OTEL_EXPORTER_CLICKHOUSE_USERNAME=default
OTEL_EXPORTER_CLICKHOUSE_PASSWORD=

# API Service
GENAI_ANALYTICS_HOST=0.0.0.0  # Use 127.0.0.1 for local-only access
GENAI_ANALYTICS_PORT=8080
GENAI_ANALYTICS_WORKERS=4
GENAI_ANALYTICS_LOG_LEVEL=INFO
GENAI_ANALYTICS_DEFAULT_TIME_RANGE_HOURS=24
GENAI_ANALYTICS_MAX_TIME_RANGE_DAYS=90
GENAI_ANALYTICS_CORS_ORIGINS=*  # Use comma-separated origins for production
```

**Security Notes:**
- The default `HOST=0.0.0.0` binds to all network interfaces. Use `127.0.0.1` for local-only access.
- The default `CORS_ORIGINS=*` allows all origins. For production, specify allowed origins: `https://app.example.com,https://admin.example.com`

## API Endpoints

### Cost Analytics
```
GET /api/v1/analytics/costs
```
Returns cost data nested by provider and model with time series.

### Token Usage
```
GET /api/v1/analytics/tokens
```
Returns token consumption patterns over time.

### Latency Analytics
```
GET /api/v1/analytics/latency
```
Returns latency percentiles (P50, P75, P90, P95, P99) by provider and model.

### Error Monitoring
```
GET /api/v1/analytics/errors
```
Returns error rates and breakdown by error type.

### Model Usage
```
GET /api/v1/analytics/models
```
Returns usage distribution across models.

### User Analytics
```
GET /api/v1/analytics/users
GET /api/v1/analytics/tenants
```
Returns per-user and per-tenant metrics.

### Session Analytics
```
GET /api/v1/analytics/sessions
```
Returns session/conversation metrics.

### Tool Analytics
```
GET /api/v1/analytics/tools
```
Returns tool/function invocation statistics.

### Provider Comparison
```
GET /api/v1/analytics/providers/compare
```
Returns comprehensive comparison across providers.

### Audit Trail
```
GET /api/v1/audit/traces
GET /api/v1/audit/traces/{trace_id}
```
Returns full trace history with detailed views.

## Common Query Parameters

All analytics endpoints support:

| Parameter | Type | Description |
|-----------|------|-------------|
| `start_time` | datetime | Start of time range (ISO8601) |
| `end_time` | datetime | End of time range (ISO8601) |
| `granularity` | enum | `minute`, `hour`, `day`, `week`, `month` |
| `service_name` | string | Filter by service |
| `provider` | string | Filter by provider |
| `model` | string | Filter by model |
| `tenant_id` | string | Filter by tenant |
| `user_id` | string | Filter by user |

## Response Format

All responses follow a nested structure by dimensions:

```json
{
  "data": {
    "openai": {
      "gpt-4": {
        "time_series": [
          {"timestamp": "2024-01-01T00:00:00Z", "cost": 12.50, "requests": 100}
        ],
        "totals": {"cost": 27.70, "requests": 220}
      }
    }
  },
  "meta": {
    "time_range": {"start": "...", "end": "..."},
    "granularity": "hour",
    "filters_applied": {"service_name": "my-app"},
    "query_time_ms": 45.2
  }
}
```

## Development

### Running Tests

```bash
pip install -e ".[test]"
pytest tests/
```

### Running Locally

```bash
pip install -e ".[dev]"
uvicorn opentelemetry.genai.analytics.main:app --reload
```

### OpenAPI Documentation

Once running, visit:
- Swagger UI: http://localhost:8080/docs
- ReDoc: http://localhost:8080/redoc
- OpenAPI JSON: http://localhost:8080/openapi.json

## Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . .
RUN pip install .

EXPOSE 8080
CMD ["genai-analytics-api"]
```

## License

Apache License 2.0
