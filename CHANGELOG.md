# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

<<<<<<< HEAD
- `opentelemetry-resource-detector-azure` Added 10s timeout to VM Resource Detector
  ([#2119](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2119))
- `opentelemetry-resource-detector-azure` Changed timeout to 4 seconds due to [timeout bug](https://github.com/open-telemetry/opentelemetry-python/issues/3644)
  ([#2136](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2136))

## Version 1.22.0/0.43b0 (2023-12-14)

### Added

- `opentelemetry-instrumentation` Added Otel semantic convention opt-in mechanism
  ([#1987](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1987))
- `opentelemetry-instrumentation-httpx` Fix mixing async and non async hooks
  ([#1920](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1920))
- `opentelemetry-instrumentation-requests` Implement new semantic convention opt-in with stable http semantic conventions
  ([#2002](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2002))
- `opentelemetry-instrument-grpc` Fix arity of context.abort for AIO RPCs
  ([#2066](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2066))
- Consolidate instrumentation suppression mechanisms and fix bug in httpx instrumentation
  ([#2061](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2061))

### Fixed

- `opentelemetry-instrumentation-httpx` Remove URL credentials
  ([#2020](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2020))
- `opentelemetry-instrumentation-urllib`/`opentelemetry-instrumentation-urllib3` Fix metric descriptions to match semantic conventions
  ([#1959](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1959))
- `opentelemetry-resource-detector-azure` Added dependency for Cloud Resource ID attribute
  ([#2072](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2072))
  
## Version 1.21.0/0.42b0 (2023-11-01)

### Added

- `opentelemetry-instrumentation-aiohttp-server` Add instrumentor and auto instrumentation support for aiohttp-server
  ([#1800](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1800))
- `opentelemetry-instrumentation-botocore` Include SNS topic ARN as a span attribute with name `messaging.destination.name` to uniquely identify the SNS topic
  ([#1995](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1995))
- `opentelemetry-instrumentation-system-metrics` Add support for collecting process metrics
  ([#1948](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1948))
- Added schema_url (`"https://opentelemetry.io/schemas/1.11.0"`) to all metrics and traces
  ([#1977](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1977))

### Fixed

- `opentelemetry-instrumentation-aio-pika` and `opentelemetry-instrumentation-pika` Fix missing trace context propagation when trace not recording.
  ([#1969](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1969))
- Fix version of Flask dependency `werkzeug`
  ([#1980](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1980))
- `opentelemetry-resource-detector-azure` Using new Cloud Resource ID attribute.
  ([#1976](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1976))
- Do not collect `system.network.connections` by default on macOS which was causing exceptions in metrics collection.
  ([#2008](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2008))

## Version 1.20.0/0.41b0 (2023-09-01)

### Fixed

- `opentelemetry-instrumentation-asgi` Fix UnboundLocalError local variable 'start' referenced before assignment
  ([#1889](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1889))
- Fixed union typing error not compatible with Python 3.7 introduced in `opentelemetry-util-http`, fix tests introduced by patch related to sanitize method for wsgi
  ([#1913](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1913))
- `opentelemetry-instrumentation-celery` Unwrap Celery's `ExceptionInfo` errors and report the actual exception that was raised. ([#1863](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1863))

### Added

- `opentelemetry-resource-detector-azure` Add resource detectors for Azure App Service and VM
  ([#1901](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1901))
- `opentelemetry-instrumentation-flask` Add support for Flask 3.0.0
  ([#152](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2013))

## Version 1.19.0/0.40b0 (2023-07-13)
- `opentelemetry-instrumentation-asgi` Add `http.server.request.size` metric
  ([#1867](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1867))

### Fixed

- `opentelemetry-instrumentation-django` Fix empty span name when using
  `path("", ...)` ([#1788](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1788)
- Fix elastic-search instrumentation sanitization to support bulk queries
  ([#1870](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1870))
- Update falcon instrumentation to follow semantic conventions
  ([#1824](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1824))
- Fix sqlalchemy instrumentation wrap methods to accept sqlcommenter options
  ([#1873](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1873))
- Exclude background task execution from root server span in ASGI middleware
  ([#1952](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1952))

### Added

- Add instrumentor support for cassandra and scylla
  ([#1902](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1902))
- Add instrumentor support for mysqlclient
  ([#1744](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1744))
- Fix async redis clients not being traced correctly
  ([#1830](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1830))
- Make Flask request span attributes available for `start_span`.
  ([#1784](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1784))
- Fix falcon instrumentation's usage of Span Status to only set the description if the status code is ERROR.
  ([#1840](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1840))
- Instrument all httpx versions >= 0.18.
  ([#1748](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1748))
- Fix `Invalid type NoneType for attribute X  (opentelemetry-instrumentation-aws-lambda)` error when some attributes do not exist
  ([#1780](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1780))
- Add metric instrumentation for celery
  ([#1679](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1679))
- `opentelemetry-instrumentation-asgi` Add `http.server.response.size` metric
  ([#1789](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1789))
- `opentelemetry-instrumentation-grpc` Allow gRPC connections via Unix socket
  ([#1833](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1833))
- Fix elasticsearch `Transport.perform_request` instrument wrap for elasticsearch >= 8
  ([#1810](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1810))
- `opentelemetry-instrumentation-urllib3` Add support for urllib3 version 2
  ([#1879](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1879))
- Add optional distro and configurator selection for auto-instrumentation
  ([#1823](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1823))

### Added
- `opentelemetry-instrumentation-kafka-python` Add instrumentation to `consume` method
  ([#1786](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1786))

## Version 1.18.0/0.39b0 (2023-05-10)

- Update runtime metrics to follow semantic conventions
  ([#1735](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1735))
- Add request and response hooks for GRPC instrumentation (client only)
  ([#1706](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1706))
- Fix memory leak in SQLAlchemy instrumentation where disposed `Engine` does not get garbage collected
  ([#1771](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1771))
- `opentelemetry-instrumentation-pymemcache` Update instrumentation to support pymemcache >4
  ([#1764](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1764))
- `opentelemetry-instrumentation-confluent-kafka` Add support for higher versions of confluent_kafka
  ([#1815](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1815))

### Added

- Expand sqlalchemy pool.name to follow the semantic conventions
  ([#1778](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1778))
- Add `excluded_urls` functionality to `urllib` and `urllib3` instrumentations
  ([#1733](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1733))
- Make Django request span attributes available for `start_span`.
  ([#1730](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1730))
- Make ASGI request span attributes available for `start_span`.
  ([#1762](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1762))
- `opentelemetry-instrumentation-celery` Add support for anonymous tasks.
  ([#1407](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1407))
- `opentelemetry-instrumentation-logging` Add `otelTraceSampled` to instrumetation-logging
  ([#1773](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1773))

### Changed

- `opentelemetry-instrumentation-botocore` now uses the AWS X-Ray propagator by default
  ([#1741](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1741))

### Fixed

- Fix redis db.statements to be sanitized by default
  ([#1778](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1778))
- Fix elasticsearch db.statement attribute to be sanitized by default
  ([#1758](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1758))
- Fix `AttributeError` when AWS Lambda handler receives a list event
  ([#1738](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1738))
- Fix `None does not implement middleware` error when there are no middlewares registered
  ([#1766](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1766))
- Fix Flask instrumentation to only close the span if it was created by the same request context.
  ([#1692](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1692))

### Changed
- Update HTTP server/client instrumentation span names to comply with spec
  ([#1759](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1759))

## Version 1.17.0/0.38b0 (2023-03-22)

### Added

- Add connection attributes to sqlalchemy connect span
  ([#1608](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1608))
- Add support for enabling Redis sanitization from environment variable
  ([#1690](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1690))
- Add metrics instrumentation for sqlalchemy
  ([#1645](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1645))

### Fixed

- Fix Flask instrumentation to only close the span if it was created by the same thread.
  ([#1654](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1654))
- Fix confluent-kafka instrumentation by allowing Producer headers to be dict or list
  ([#1655](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1655))
- `opentelemetry-instrumentation-system-metrics` Fix initialization of the instrumentation class when configuration is provided
  ([#1438](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1439))
- Fix exception in Urllib3 when dealing with filelike body.
  ([#1399](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1399))
- Fix httpx resource warnings
  ([#1695](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1695))

### Changed

- `opentelemetry-instrumentation-requests` Replace `name_callback` and `span_callback` with standard `response_hook` and `request_hook` callbacks
  ([#670](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/670))

## Version 1.16.0/0.37b0 (2023-02-17)

### Added

- Support `aio_pika` 9.x (([#1670](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1670])
- `opentelemetry-instrumentation-redis` Add `sanitize_query` config option to allow query sanitization.  ([#1572](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1572))
- `opentelemetry-instrumentation-elasticsearch` Add optional db.statement query sanitization.
  ([#1598](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1598))
- `opentelemetry-instrumentation-celery` Record exceptions as events on the span.
  ([#1573](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1573))
- Add metric instrumentation for urllib
  ([#1553](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1553))
- `opentelemetry/sdk/extension/aws` Implement [`aws.ecs.*`](https://github.com/open-telemetry/opentelemetry-specification/blob/main/specification/resource/semantic_conventions/cloud_provider/aws/ecs.md) and [`aws.logs.*`](https://opentelemetry.io/docs/reference/specification/resource/semantic_conventions/cloud_provider/aws/logs/) resource attributes in the `AwsEcsResourceDetector` detector when the ECS Metadata v4 is available
  ([#1212](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1212))
- `opentelemetry-instrumentation-aio-pika` Support `aio_pika` 8.x
  ([#1481](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1481))
- `opentelemetry-instrumentation-aws-lambda` Flush `MeterProvider` at end of function invocation.
  ([#1613](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1613))
- Fix aiohttp bug with unset `trace_configs`
  ([#1592](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1592))
- `opentelemetry-instrumentation-django` Allow explicit `excluded_urls` configuration through `instrument()`
  ([#1618](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1618))

### Fixed

- Fix TortoiseORM instrumentation `AttributeError: type object 'Config' has no attribute 'title'`
  ([#1575](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1575))
- Fix SQLAlchemy uninstrumentation
  ([#1581](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1581))
- `opentelemetry-instrumentation-grpc` Fix code()/details() of _OpentelemetryServicerContext.
  ([#1578](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1578))
- Fix aiopg instrumentation to work with aiopg < 2.0.0
  ([#1473](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1473))
- `opentelemetry-instrumentation-aws-lambda` Adds an option to configure `disable_aws_context_propagation` by
  environment variable: `OTEL_LAMBDA_DISABLE_AWS_CONTEXT_PROPAGATION`
  ([#1507](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1507))
- Fix pymongo to collect the property DB_MONGODB_COLLECTION
  ([#1555](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1555))
- `opentelemetry-instrumentation-asgi` Fix keys() in class ASGIGetter to correctly fetch values from carrier headers.
  ([#1435](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1435))
- mongo db - fix db statement capturing
  ([#1512](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1512))
- Add commit method for ConfluentKafkaInstrumentor's ProxiedConsumer
  ([#1656](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1656))

## Version 1.15.0/0.36b0 (2022-12-10)

- Add uninstrument test for sqlalchemy
  ([#1471](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1471))
- `opentelemetry-instrumentation-tortoiseorm` Initial release
  ([#685](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/685))
- Add metric instrumentation for tornado
  ([#1252](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1252))
- `opentelemetry-instrumentation-aws-lambda` Add option to disable aws context propagation
  ([#1466](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1466))

### Added

- `opentelemetry-resource-detector-container` Add support resource detection of container properties.
  ([#1584](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1584))
- `opentelemetry-instrumentation-pymysql` Add tests for commit() and rollback().
  ([#1424](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1424))
- `opentelemetry-instrumentation-fastapi` Add support for regular expression matching and sanitization of HTTP headers.
  ([#1403](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1403))
- `opentelemetry-instrumentation-botocore` add support for `messaging.*` in the sqs extension.
  ([#1350](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1350))
- `opentelemetry-instrumentation-starlette` Add support for regular expression matching and sanitization of HTTP headers.
  ([#1404](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1404))
- `opentelemetry-instrumentation-botocore` Add support for SNS `publish` and `publish_batch`.
  ([#1409](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1409))
- Strip leading comments from SQL queries when generating the span name.
  ([#1434](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1434))
- `opentelemetry-instrumentation-confluent-kafka` Add support for the latest versions of the library.
  ([#1468](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1468))

### Fixed

- Fix bug in Urllib instrumentation - add status code to span attributes only if the status code is not None.
  ([#1430](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1430))
- `opentelemetry-instrumentation-aiohttp-client` Allow overriding of status in response hook.
  ([#1394](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1394))
- `opentelemetry-instrumentation-pymysql` Fix dbapi connection instrument wrapper has no _sock member.
  ([#1424](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1424))
- `opentelemetry-instrumentation-dbapi` Fix the check for the connection already being instrumented in instrument_connection().
  ([#1424](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1424))
- Remove db.name attribute from Redis instrumentation
  ([#1427](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1427))
- `opentelemetry-instrumentation-asgi` Fix target extraction for duration metric
  ([#1461](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1461))
- Add grpc.aio instrumentation to package entry points
  ([#1442](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1442))
- Fix a bug in SQLAlchemy instrumentation - support disabling enable_commenter variable
  ([#1440](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1440))

## Version 1.14.0/0.35b0 (2022-11-03)

### Deprecated

- `opentelemetry-distro` Deprecate `otlp_proto_grpc` and `otlp_proto_http` in favor of using
  `OTEL_EXPORTER_OTLP_TRACES_PROTOCOL` as according to specifications
  ([#1250](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1250))

### Added

- Capture common HTTP attributes from API Gateway proxy events in `opentelemetry-instrumentation-aws-lambda`
  ([#1233](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1233))
- Add metric instrumentation for tornado
  ([#1252](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1252))
- `opentelemetry-instrumentation-django` Fixed bug where auto-instrumentation fails when django is installed and settings are not configured.
  ([#1369](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1369))
- `opentelemetry-instrumentation-system-metrics` add supports to collect system thread count. ([#1339](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1339))
- `opentelemetry-exporter-richconsole` Fixing RichConsoleExpoter to allow multiple traces, fixing duplicate spans and include resources ([#1336](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1336))
- `opentelemetry-instrumentation-asgi` Add support for regular expression matching and sanitization of HTTP headers.
  ([#1333](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1333))
- `opentelemetry-instrumentation-asgi` metrics record target attribute (FastAPI only)
  ([#1323](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1323))
- `opentelemetry-instrumentation-wsgi` Add support for regular expression matching and sanitization of HTTP headers.
  ([#1402](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1402))
- Add support for py3.11
  ([#1415](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1415))
- `opentelemetry-instrumentation-django` Add support for regular expression matching and sanitization of HTTP headers.
  ([#1411](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1411))
- `opentelemetry-instrumentation-falcon` Add support for regular expression matching and sanitization of HTTP headers.
  ([#1412](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1412))
- `opentelemetry-instrumentation-flask` Add support for regular expression matching and sanitization of HTTP headers.
  ([#1413](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1413))
- `opentelemetry-instrumentation-pyramid` Add support for regular expression matching and sanitization of HTTP headers.
  ([#1414](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1414))
- `opentelemetry-instrumentation-grpc` Add support for grpc.aio Clients and Servers
  ([#1245](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1245))
- Add metric exporter for Prometheus Remote Write
  ([#1359](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1359))

### Fixed

- Fix bug in Falcon instrumentation
  ([#1377](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1377))
- `opentelemetry-instrumentation-asgi` Fix keys() in class ASGIGetter so it decodes the keys before returning them.
  ([#1333](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1333))
- `opentelemetry-instrumentation-asgi` Make ASGIGetter.get() compare all keys in a case insensitive manner.
  ([#1333](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1333))
- Use resp.text instead of resp.body for Falcon 3 to avoid a deprecation warning.
  ([#1412](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1412))

## Version 1.13.0/0.34b0 (2022-09-26)

- `opentelemetry-instrumentation-asyncpg` Fix high cardinality in the span name
  ([#1324](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1324))

### Added

- `opentelemetry-instrumentation-grpc` add supports to filter requests to instrument.
  ([#1241](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1241))
- Flask sqlalchemy psycopg2 integration
  ([#1224](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1224))
- Add metric instrumentation in Falcon
  ([#1230](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1230))
- Add metric instrumentation in fastapi
  ([#1199](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1199))
- Add metric instrumentation in Pyramid
  ([#1242](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1242))
- `opentelemetry-util-http` Add support for sanitizing HTTP header values.
  ([#1253](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1253))
- Add metric instrumentation in starlette
  ([#1327](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1327))


### Fixed

- `opentelemetry-instrumentation-kafka-python`: wait for metadata
  ([#1260](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1260))
- `opentelemetry-instrumentation-boto3sqs` Make propagation compatible with other SQS instrumentations, add 'messaging.url' span attribute, and fix missing package dependencies.
  ([#1234](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1234))
- `opentelemetry-instrumentation-pymongo` Change span names to not contain queries but only database name and command name
  ([#1247](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1247))
- restoring metrics in django framework
  ([#1208](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1208))
- `opentelemetry-instrumentation-aiohttp-client` Fix producing additional spans with each newly created ClientSession
- ([#1246](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1246))
- Add _is_opentelemetry_instrumented check in _InstrumentedFastAPI class
  ([#1313](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1313))
- Fix uninstrumentation of existing app instances in FastAPI
  ([#1258](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1258))
- Fix uninstrumentation of existing app instances in falcon
  ([#1341]https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1341)

## Version 1.12.0/0.33b0 (2022-08-08)

- Adding multiple db connections support for django-instrumentation's sqlcommenter
  ([#1187](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1187))
- SQLCommenter semicolon bug fix
  ([#1200](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1200/files))
- Adding sqlalchemy native tags in sqlalchemy commenter
  ([#1206](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1206))
- Add psycopg2 native tags to sqlcommenter
  ([#1203](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1203))

### Added
- `opentelemetry-instrumentation-redis` add support to instrument RedisCluster clients
  ([#1177](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1177))
- `opentelemetry-instrumentation-sqlalchemy` Added span for the connection phase ([#1133](https://github.com/open-telemetry/opentelemetry-python-contrib/issues/1133))
- Add metric instrumentation in asgi
  ([#1197](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1197))
- Add metric instrumentation for flask
  ([#1186](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1186))
- Add a test for asgi using NoOpTracerProvider
  ([#1367](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1367))

## [1.12.0rc2-0.32b0](https://github.com/open-telemetry/opentelemetry-python/releases/tag/v1.12.0rc2-0.32b0) - 2022-07-01


- Pyramid: Only categorize 500s server exceptions as errors
  ([#1037](https://github.com/open-telemetry/opentelemetry-python-contrib/issues/1037))

### Fixed
- Fix bug in system metrics by checking their configuration
  ([#1129](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1129))
- Adding escape call to fix [auto-instrumentation not producing spans on Windows](https://github.com/open-telemetry/opentelemetry-python/issues/2703).
  ([#1100](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1100))
- `opentelemetry-instrumentation-grpc` narrow protobuf dependency to exclude protobuf >= 4
  ([#1109](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1109))
- cleanup type hints for textmap `Getter` and `Setter` classes
- Suppressing downstream HTTP instrumentation to avoid [extra spans](https://github.com/open-telemetry/opentelemetry-python-contrib/issues/930)
  ([#1116](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1116))
- fixed typo in `system.network.io` metric configuration
  ([#1135](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1135))


### Added
- `opentelemetry-instrumentation-aiohttp-client` Add support for optional custom trace_configs argument.
  ([1079](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1079))
- `opentelemetry-instrumentation-sqlalchemy` add support to instrument multiple engines
  ([#1132](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1132))
- `opentelemetry-instrumentation-logging` add log hook support
  ([#1117](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1117))
- `opentelemetry-instrumentation-remoulade` Initial release
  ([#1082](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1082))
- Added `opentelemetry-instrumention-confluent-kafka`
  ([#1111](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1111))
- Set otlp-proto-grpc as the default metrics exporter for auto-instrumentation
  ([#1127](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1127))
- Add metric instrumentation for WSGI
  ([#1128](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1128))
- Add metric instrumentation for Urllib3
  ([#1198](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1198))
- `opentelemetry-instrumentation-aio-pika` added RabbitMQ aio-pika module instrumentation.
  ([#1095](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1095))
- `opentelemetry-instrumentation-requests` Restoring metrics in requests
  ([#1110](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1110))
- Integrated sqlcommenter plugin into opentelemetry-instrumentation-django
  ([#896](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/896))


## Version 1.12.0rc1/0.31b0 (2022-05-17)

### Fixed
- `opentelemetry-instrumentation-aiohttp-client` make span attributes available to sampler
  ([#1072](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1072))
- `opentelemetry-instrumentation-aws-lambda` Fixed an issue - in some rare cases (API GW proxy integration test)
  headers are set to None, breaking context propagators.
  ([#1055](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1055))
- Refactoring custom header collection API for consistency
  ([#1064](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1064))
- `opentelemetry-instrumentation-sqlalchemy` will correctly report `otel.library.name`
  ([#1086](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1086))
- `opentelemetry-sdk-extension-aws` change timeout for AWS EC2 and EKS metadata requests from 1000 seconds and 2000 seconds to 1 second

### Added
- `opentelemetry-instrument` and `opentelemetry-bootstrap` now include a `--version` flag
  ([#1065](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1065))
- `opentelemetry-instrumentation-redis` now instruments asynchronous Redis clients, if the installed redis-py includes async support (>=4.2.0).
  ([#1076](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1076))
- `opentelemetry-instrumentation-boto3sqs` added AWS's SQS instrumentation.
  ([#1081](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1081))


## Version 1.11.1/0.30b1 (2022-04-21)

### Added
- `opentelemetry-instrumentation-starlette` Capture custom request/response headers in span attributes
  ([#1046](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1046))

### Fixed
- Prune autoinstrumentation sitecustomize module directory from PYTHONPATH immediately
  ([#1066](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1066))


## Version 1.11.0/0.30b0 (2022-04-18)

### Fixed
- `opentelemetry-instrumentation-pyramid` Fixed which package is the correct caller in _traced_init.
  ([#830](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/830))
- `opentelemetry-instrumentation-tornado` Fix Tornado errors mapping to 500
  ([#1048](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1048))
- `opentelemetry-instrumentation-urllib` make span attributes available to sampler
  ([1014](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1014))
- `opentelemetry-instrumentation-flask` Fix non-recording span bug
  ([#999](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/999))
- `opentelemetry-instrumentation-tornado` Fix non-recording span bug
  ([#999](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/999))

### Added

- `opentelemetry-instrumentation-fastapi` Capture custom request/response headers in span attributes
  ([#1032](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1032))
- `opentelemetry-instrumentation-django` Capture custom request/response headers in span attributes
  ([#1024](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1024))
- `opentelemetry-instrumentation-asgi` Capture custom request/response headers in span attributes
  ([#1004](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1004))
- `opentelemetry-instrumentation-psycopg2` extended the sql commenter support of dbapi into psycopg2
  ([#940](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/940))
- `opentelemetry-instrumentation-falcon` Add support for falcon==1.4.1
  ([#1000](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1000))
- `opentelemetry-instrumentation-falcon` Falcon: Capture custom request/response headers in span attributes
  ([#1003](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1003))
- `opentelemetry-instrumentation-elasticsearch` no longer creates unique span names by including search target, replaces them with `<target>` and puts the value in attribute `elasticsearch.target`
  ([#1018](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1018))
- `opentelemetry-instrumentation-pyramid` Handle non-HTTPException exceptions
  ([#1001](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1001))
- `opentelemetry-instrumentation-system-metrics` restore `SystemMetrics` instrumentation as `SystemMetricsInstrumentor`
  ([#1012](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1012))
- `opentelemetry-instrumentation-pyramid` Pyramid: Capture custom request/response headers in span attributes
  ([#1022](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1022))


## Version 1.10.0/0.29b0 (2022-03-10)

- `opentelemetry-instrumentation-wsgi` Capture custom request/response headers in span attributes
  ([#925](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/925))
- `opentelemetry-instrumentation-flask` Flask: Capture custom request/response headers in span attributes
  ([#952](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/952))
- `opentelemetry-instrumentation-tornado` Tornado: Capture custom request/response headers in span attributes
  ([#950](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/950))

### Added

- `opentelemetry-instrumentation-aws-lambda` `SpanKind.SERVER` by default, add more cases for `SpanKind.CONSUMER` services. ([#926](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/926))
- `opentelemetry-instrumentation-sqlalchemy` added experimental sql commenter capability
   ([#924](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/924))
- `opentelemetry-contrib-instrumentations` added new meta-package that installs all contrib instrumentations.
  ([#681](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/681))
- `opentelemetry-instrumentation-dbapi` add experimental sql commenter capability
  ([#908](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/908))
- `opentelemetry-instrumentation-requests` make span attribute available to samplers
  ([#931](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/931))
- `opentelemetry-datadog-exporter` add deprecation note to example.
  ([#900](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/900))

### Fixed

- `opentelemetry-instrumentation-dbapi` Changed the format of traceparent id.
  ([#941](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/941))
- `opentelemetry-instrumentation-logging` retrieves service name defensively.
  ([#890](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/890))
- `opentelemetry-instrumentation-wsgi` WSGI: Conditionally create SERVER spans
  ([#903](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/903))
- `opentelemetry-instrumentation-falcon` Safer patching mechanism
  ([#895](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/895))
- `opentelemetry-instrumentation-kafka-python` Fix topic extraction
  ([#949](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/949))

### Changed

- `opentelemetry-instrumentation-pymemcache` should run against newer versions of pymemcache.
  ([#935](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/935))

## Version 1.9.1/0.28b1 (2022-01-29)

### Fixed

- `opentelemetry-instrumentation-pika` requires `packaging` dependency

- `opentelemetry-instrumentation-tornado` Tornado: Conditionally create SERVER spans
  ([#889](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/889))

## Version 1.9.0/0.28b0 (2022-01-26)


### Added

- `opentelemetry-instrumentation-pyramid` Pyramid: Conditionally create SERVER spans
  ([#869](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/869))
- `opentelemetry-instrumentation-grpc` added `trailing_metadata` to _OpenTelemetryServicerContext.
  ([#871](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/871))
- `opentelemetry-instrumentation-asgi` now returns a `traceresponse` response header.
  ([#817](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/817))
- `opentelemetry-instrumentation-kafka-python` added kafka-python module instrumentation.
  ([#814](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/814))
- `opentelemetry-instrumentation-falcon` Falcon: Conditionally create SERVER spans
  ([#867](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/867))
- `opentelemetry-instrumentation-pymongo` now supports `pymongo v4`
  ([#876](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/876))

- `opentelemetry-instrumentation-httpx` now supports versions higher than `0.19.0`.
  ([#866](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/866))

### Fixed

- `opentelemetry-instrumentation-django` Django: Conditionally create SERVER spans
  ([#832](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/832))
- `opentelemetry-instrumentation-flask` Flask: Conditionally create SERVER spans
  ([#828](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/828))
- `opentelemetry-instrumentation-celery` Celery: Support partial task time limit
  ([#846](https://github.com/open-telemetry/opentelemetry-python-contrib/issues/846))
- `opentelemetry-instrumentation-asgi` ASGI: Conditionally create SERVER spans
  ([#843](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/843))
- `opentelemetry-instrumentation-django` Django: fix issue preventing detection of MIDDLEWARE_CLASSES
- `opentelemetry-instrumentation-sqlite3` Instrumentation now works with `dbapi2.connect`
- `opentelemetry-instrumentation-kafka` Kafka: safe kafka partition extraction
  ([#872](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/872))
- `opentelemetry-instrumentation-aiohttp-client` aiohttp: Correct url filter input type
  ([#843](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/864))

- `opentelemetry-instrumentation-aiohttp-client` aiohttp: Remove `span_name` from docs
  ([#857](https://github.com/open-telemetry/opentelemetry-python-contrib/issues/857))


## Version 1.8.0/0.27b0 (2021-12-17)

### Added

- `opentelemetry-instrumentation-aws-lambda` Adds support for configurable flush timeout  via `OTEL_INSTRUMENTATION_AWS_LAMBDA_FLUSH_TIMEOUT` property. ([#825](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/825))
- `opentelemetry-instrumentation-pika` Adds support for versions between `0.12.0` to `1.0.0`. ([#837](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/837))

### Fixed

- `opentelemetry-instrumentation-urllib` Fixed an error on unexpected status values.
  ([#823](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/823))

- `opentelemetry-exporter-richconsole` Fixed attribute error on parentless spans.
  ([#782](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/782))

- `opentelemetry-instrumentation-tornado` Add support instrumentation for Tornado 5.1.1
  ([#812](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/812))

## Version 1.7.1/0.26b1 (2021-11-11)

### Added

- `opentelemetry-instrumentation-aws-lambda` Add instrumentation for AWS Lambda Service - pkg metadata files (Part 1/2)
  ([#739](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/739))
- Add support for Python 3.10
  ([#742](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/742))
- Pass in auto-instrumentation version to configurator
  ([#783](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/783))
- `opentelemetry-instrumentation` Add `setuptools` to `install_requires`
  ([#781](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/781))
- `opentelemetry-instrumentation-aws-lambda` Add instrumentation for AWS Lambda Service - Implementation (Part 2/2)
  ([#777](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/777))
- `opentelemetry-instrumentation-pymongo` Add `request_hook`, `response_hook` and `failed_hook` callbacks passed as arguments to the instrument method
  ([#793](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/793))
- `opentelemetry-instrumentation-pymysql` Add support for PyMySQL 1.x series
  ([#792](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/792))
- Add support for generic OTEL_PYTHON_EXCLUDED_URLS variable
  ([#790](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/790))

### Fixed

- `opentelemetry-instrumentation-asgi` now explicitly depends on asgiref as it uses the package instead of instrumenting it.
  ([#765](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/765))
- `opentelemetry-instrumentation-pika` now propagates context to basic_consume callback
  ([#766](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/766))
- `opentelemetry-instrumentation-falcon` Dropped broken support for Python 3.4.
  ([#774](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/774))
- `opentelemetry-instrumentation-django` Fixed carrier usage on ASGI requests.
  ([#767](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/767))
- Don't set Span Status on 4xx http status code for SpanKind.SERVER spans
  ([#776](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/776))
- `opentelemetry-instrumentation-django` Fixed instrumentation and tests for all Django major versions.
  ([#780](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/780))

## Version 1.6.2/0.25b2 (2021-10-19)

- `opentelemetry-instrumentation-sqlalchemy` Fix PostgreSQL instrumentation for Unix sockets
  ([#761](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/761))

### Changed

- `opentelemetry-sdk-extension-aws` & `opentelemetry-propagator-aws` Release AWS Python SDK Extension as 2.0.1 and AWS Propagator as 1.0.1
  ([#753](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/753))
- `opentelemetry-instrumentation-pika` Add `_decorate_basic_consume` to ensure post instrumentation `basic_consume` calls are also instrumented.
  ([#759](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/759))
- Consolidate instrumentation documentation in docstrings
  ([#754](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/754))

### Fixed

- `opentelemetry-distro` uses the correct entrypoint name which was updated in the core release of 1.6.0 but the distro was not updated with it
  ([#755](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/755))

### Added
- `opentelemetry-instrumentation-pika` Add `publish_hook` and `consume_hook` callbacks passed as arguments to the instrument method
  ([#763](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/763))


## Version 1.6.1/0.25b1 (2021-10-18)

### Changed
- `opentelemetry-util-http` no longer contains an instrumentation entrypoint and will not be loaded
  automatically by the auto instrumentor.
  ([#745](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/745))
- `opentelemetry-instrumentation-pika` Bugfix use properties.headers. It will prevent the header injection from raising.
  ([#740](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/740))
- `opentelemetry-instrumentation-botocore` Add extension for DynamoDB
  ([#735](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/735))
- `opentelemetry-sdk-extension-aws` & `opentelemetry-propagator-aws` Remove unnecessary dependencies on `opentelemetry-test`
  ([#752](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/752))
- `opentelemetry-instrumentation-botocore` Add Lambda extension
  ([#760](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/760))

## Version 1.6.0/0.25b0 (2021-10-13)
### Added
- `opentelemetry-sdk-extension-aws` Release AWS Python SDK Extension as 1.0.0
  ([#667](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/667))
- `opentelemetry-instrumentation-urllib3`, `opentelemetry-instrumentation-requests`
  The `net.peer.ip` attribute is set to the IP of the connected HTTP server or proxy
  using a new instrumentor in `opententelemetry-util-http`
  ([#661](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/661))
- `opentelemetry-instrumentation-pymongo` Add check for suppression key in PyMongo.
  ([#736](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/736))
- `opentelemetry-instrumentation-elasticsearch` Added `response_hook` and `request_hook` callbacks
  ([#670](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/670))
- `opentelemetry-instrumentation-redis` added request_hook and response_hook callbacks passed as arguments to the instrument method.
  ([#669](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/669))
- `opentelemetry-instrumentation-botocore` add `request_hook` and `response_hook` callbacks
  ([679](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/679))
- `opentelemetry-exporter-richconsole` Initial release
  ([#686](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/686))
- `opentelemetry-instrumentation-elasticsearch` no longer creates unique span names by including document IDs, replaces them with `:id` and puts the value in attribute `elasticsearch.id`
  ([#705](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/705))
- `opentelemetry-instrumentation-tornado` now sets `http.client_ip` and `tornado.handler` attributes
  ([#706](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/706))
- `opentelemetry-instrumentation-requests` added exclude urls functionality
  ([#714](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/714))
- `opentelemetry-instrumentation-django` Add ASGI support
  ([#391](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/391))

### Changed
- `opentelemetry-instrumentation-flask` Fix `RuntimeError: Working outside of request context`
  ([#734](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/734))
- `opentelemetry-propagators-aws-xray` Rename `AwsXRayFormat` to `AwsXRayPropagator`
  ([#729](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/729))
- `opentelemetry-instrumentation-sqlalchemy` Respect provided tracer provider when instrumenting SQLAlchemy
  ([#728](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/728))
- `opentelemetry-sdk-extension-aws` Move AWS X-Ray Propagator into its own `opentelemetry-propagators-aws` package
  ([#720](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/720))
- `opentelemetry-instrumentation-sqlalchemy` Added `packaging` dependency
  ([#713](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/713))
- `opentelemetry-instrumentation-jinja2` Allow instrumentation of newer Jinja2 versions.
  ([#712](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/712))
- `opentelemetry-instrumentation-botocore` Make common span attributes compliant with semantic conventions
  ([#674](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/674))
- `opentelemetry-sdk-extension-aws` Release AWS Python SDK Extension as 1.0.0
  ([#667](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/667))
- `opentelemetry-instrumentation-botocore` Unpatch botocore Endpoint.prepare_request on uninstrument
  ([#664](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/664))
- `opentelemetry-instrumentation-botocore` Fix span injection for lambda invoke
  ([#663](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/663))
- `opentelemetry-instrumentation-botocore` Introduce instrumentation extensions
  ([#718](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/718))
- `opentelemetry-instrumentation-urllib3` Updated `_RequestHookT` with two additional fields - the request body and the request headers
  ([#660](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/660))
- Tests for Falcon 3 support
  ([#644](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/644))

## Version 1.5.0/0.24b0 (2021-08-26)

### Added
- `opentelemetry-sdk-extension-aws` Add AWS resource detectors to extension package
  ([#586](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/586))
- `opentelemetry-instrumentation-asgi`, `opentelemetry-instrumentation-aiohttp-client`, `openetelemetry-instrumentation-fastapi`,
  `opentelemetry-instrumentation-starlette`, `opentelemetry-instrumentation-urllib`, `opentelemetry-instrumentation-urllib3` Added `request_hook` and `response_hook` callbacks
  ([#576](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/576))
- `opentelemetry-instrumentation-pika` added RabbitMQ's pika module instrumentation.
  ([#680](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/680))

### Changed

- `opentelemetry-instrumentation-fastapi` Allow instrumentation of newer FastAPI versions.
  ([#602](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/602))
- Enable explicit `excluded_urls` argument in `opentelemetry-instrumentation-flask`
  ([#604](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/604))

## Version 1.4.0/0.23b0 (2021-07-21)

### Removed
- Move `opentelemetry-instrumentation` to the core repo.
  ([#595](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/595))

### Changed
- `opentelemetry-instrumentation-falcon` added support for Falcon 3.
  ([#607](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/607))
- `opentelemetry-instrumentation-tornado` properly instrument work done in tornado on_finish method.
  ([#499](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/499))
- `opentelemetry-instrumentation` Fixed cases where trying to use an instrumentation package without the
  target library was crashing auto instrumentation agent.
  ([#530](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/530))
- Fix weak reference error for pyodbc cursor in SQLAlchemy instrumentation.
  ([#469](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/469))
- Implemented specification that HTTP span attributes must not contain username and password.
  ([#538](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/538))
- Changed the psycopg2-binary to psycopg2 as dependency in production
  ([#543](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/543))
- Implement consistent way of checking if instrumentation is already active
  ([#549](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/549))
- Require aiopg to be less than 1.3.0
  ([#560](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/560))
- `opentelemetry-instrumentation-django` Migrated Django middleware to new-style.
  ([#533](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/533))
- Updating dependency for opentelemetry api/sdk packages to support major version instead
  of pinning to specific versions.
  ([#567](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/567))
- `opentelemetry-instrumentation-grpc` Respect the suppress instrumentation in gRPC client instrumentor
  ([#559](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/559))
- `opentelemetry-instrumentation-grpc` Fixed asynchronous unary call traces
  ([#536](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/536))
- `opentelemetry-sdk-extension-aws` Update AWS entry points to match spec
  ([#566](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/566))
- Include Flask 2.0 as compatible with existing flask instrumentation
  ([#545](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/545))
- `openelemetry-sdk-extension-aws` Take a dependency on `opentelemetry-sdk`
  ([#558](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/558))
- Change `opentelemetry-instrumentation-httpx` to replace `client` classes with instrumented versions.
  ([#577](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/577))
- `opentelemetry-instrumentation-requests` Fix potential `AttributeError` when `requests`
  is used with a custom transport adapter.
  ([#562](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/562))
- `opentelemetry-instrumentation-django` Fix AttributeError: ResolverMatch object has no attribute route
  ([#581](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/581))
- `opentelemetry-instrumentation-botocore` Suppress botocore downstream instrumentation like urllib3
  ([#563](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/563))
- `opentelemetry-exporter-datadog` Datadog exporter should not use `unknown_service` as fallback resource service name.
  ([#570](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/570))
- Add support for the async extension of SQLAlchemy (>= 1.4)
  ([#568](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/568))

### Added
- `opentelemetry-instrumentation-httpx` Add `httpx` instrumentation
  ([#461](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/461))

## Version 1.3.0/0.22b0 (2021-06-01)

### Changed
- `opentelemetry-bootstrap` not longer forcibly removes and re-installs libraries and their instrumentations.
  This means running bootstrap will not auto-upgrade existing dependencies and as a result not cause dependency
  conflicts.
  ([#514](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/514))
- `opentelemetry-instrumentation-asgi` Set the response status code on the server span
  ([#478](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/478))
- `opentelemetry-instrumentation-tornado` Fixed cases where description was used with non-
  error status code when creating Status objects.
  ([#504](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/504))
- `opentelemetry-instrumentation-asgi` Fix instrumentation default span name.
  ([#418](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/418))
- Propagators use the root context as default for `extract` and do not modify
  the context if extracting from carrier does not work.
  ([#488](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/488))

### Added
- `opentelemetry-instrumentation-botocore` now supports
  context propagation for lambda invoke via Payload embedded headers.
  ([#458](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/458))
- Added support for CreateKey functionality.
  ([#502](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/502))

## Version 1.2.0/0.21b0 (2021-05-11)

### Changed
- Instrumentation packages don't specify the libraries they instrument as dependencies
  anymore. Instead, they verify the correct version of libraries are installed at runtime.
  ([#475](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/475))
- `opentelemetry-propagator-ot-trace` Use `TraceFlags` object in `extract`
  ([#472](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/472))
- Set the `traced_request_attrs` of FalconInstrumentor by an argument correctly.
  ([#473](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/473))
- Enable passing explicit urls to exclude in instrumentation in FastAPI
  ([#486](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/486))
- Distros can now implement `load_instrumentor(EntryPoint)` method to customize instrumentor
  loading behaviour.
  ([#480](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/480))
- Fix entrypoint for ottrace propagator
  ([#492](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/492))

### Added

- Move `opentelemetry-instrumentation` from core repository
  ([#465](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/465))

## Version 0.20b0 (2021-04-20)

### Changed

- Restrict DataDog exporter's `ddtrace` dependency to known working versions.
  ([#400](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/400))
- GRPC instrumentation now correctly injects trace context into outgoing requests.
  ([#392](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/39))
- Publish `opentelemetry-propagator-ot-trace` package as a part of the release process
  ([#387](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/387))
- Update redis instrumentation to follow semantic conventions
  ([#403](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/403))
- Update instrumentations to use tracer_provider for creating tracer if given, otherwise use global tracer provider
  ([#402](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/402))
- `opentelemetry-instrumentation-wsgi` Replaced `name_callback` with `request_hook`
  and `response_hook` callbacks.
  ([#424](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/424))
- Update gRPC instrumentation to better wrap server context
  ([#420](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/420))
- `opentelemetry-instrumentation-redis` Fix default port KeyError and Wrong Attribute name (net.peer.ip -> net.peer.port)
  ([#265](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/265))
- `opentelemetry-instrumentation-asyncpg` Fix default port KeyError and Wrong Attribute name (net.peer.ip -> net.peer.port)
  ([#265](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/265))

### Added

- `opentelemetry-instrumentation-urllib3` Add urllib3 instrumentation
  ([#299](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/299))

- `opentelemetry-instrumentation-flask` Added `request_hook` and `response_hook` callbacks.
  ([#416](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/416))

- `opentelemetry-instrumenation-django` now supports request and response hooks.
  ([#407](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/407))
- `opentelemetry-instrumentation-falcon` FalconInstrumentor now supports request/response hooks.
  ([#415](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/415))
- `opentelemetry-instrumentation-tornado` Add request/response hooks.
  ([#426](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/426))
- `opentelemetry-exporter-datadog` Add parsing exception events for error tags.
  ([#459](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/459))
- `opentelemetry-instrumenation-django` now supports trace response headers.
  ([#436](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/436))
- `opentelemetry-instrumenation-tornado` now supports trace response headers.
  ([#436](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/436))
- `opentelemetry-instrumenation-pyramid` now supports trace response headers.
  ([#436](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/436))
- `opentelemetry-instrumenation-falcon` now supports trace response headers.
  ([#436](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/436))
- `opentelemetry-instrumenation-flask` now supports trace response headers.
  ([#436](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/436))
- `opentelemetry-instrumentation-grpc` Keep client interceptor in sync with grpc client interceptors.
  ([#442](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/442))

### Removed

- Remove `http.status_text` from span attributes
  ([#406](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/406))

## Version 0.19b0 (2021-03-26)

- Implement context methods for `_InterceptorChannel`
  ([#363](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/363))

### Changed

- Rename `IdsGenerator` to `IdGenerator`
  ([#350](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/350))
- `opentelemetry-exporter-datadog` Fix warning when DatadogFormat encounters a request with
  no DD_ORIGIN headers ([#368](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/368)).
- `opentelemetry-instrumentation-aiopg` Fix multiple nested spans when
  `aiopg.pool` is used
  ([#336](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/381)).
- Updated instrumentations to use `opentelemetry.trace.use_span` instead of `Tracer.use_span()`
  ([#364](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/364))
- `opentelemetry-propagator-ot-trace` Do not throw an exception when headers are not present
  ([#378](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/378))
- `opentelemetry-instrumentation-wsgi` Reimplement `keys` method to return actual keys from the carrier instead of an empty list.
  ([#379](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/379))
- `opentelemetry-instrumentation-sqlalchemy` Fix multithreading issues in recording spans from SQLAlchemy
  ([#315](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/315))
- Make getters and setters optional
  ([#372](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/372))
=======
- Handle HTTP 2XX responses as successful in OTLP exporters
  ([#3623](https://github.com/open-telemetry/opentelemetry-python/pull/3623))
- Improve Resource Detector timeout messaging
  ([#3645](https://github.com/open-telemetry/opentelemetry-python/pull/3645))

## Version 1.22.0/0.43b0 (2023-12-15)

- Prometheus exporter sanitize info metric
  ([#3572](https://github.com/open-telemetry/opentelemetry-python/pull/3572))
- Remove Jaeger exporters
  ([#3554](https://github.com/open-telemetry/opentelemetry-python/pull/3554))
- Log stacktrace on `UNKNOWN` status OTLP export error 
  ([#3536](https://github.com/open-telemetry/opentelemetry-python/pull/3536))
- Fix OTLPExporterMixin shutdown timeout period
  ([#3524](https://github.com/open-telemetry/opentelemetry-python/pull/3524))
- Handle `taskName` `logrecord` attribute
  ([#3557](https://github.com/open-telemetry/opentelemetry-python/pull/3557))

## Version 1.21.0/0.42b0 (2023-11-01)

- Fix `SumAggregation`
￼  ([#3390](https://github.com/open-telemetry/opentelemetry-python/pull/3390))
- Fix handling of empty metric collection cycles
  ([#3335](https://github.com/open-telemetry/opentelemetry-python/pull/3335))
- Fix error when no LoggerProvider configured for LoggingHandler
  ([#3423](https://github.com/open-telemetry/opentelemetry-python/pull/3423))
- Make `opentelemetry_metrics_exporter` entrypoint support pull exporters
  ([#3428](https://github.com/open-telemetry/opentelemetry-python/pull/3428))
- Allow instrument names to have '/' and up to 255 characters
  ([#3442](https://github.com/open-telemetry/opentelemetry-python/pull/3442))
- Do not load Resource on sdk import
  ([#3447](https://github.com/open-telemetry/opentelemetry-python/pull/3447))
- Update semantic conventions to version 1.21.0
  ([#3251](https://github.com/open-telemetry/opentelemetry-python/pull/3251))
- Add missing schema_url in global api for logging and metrics
  ([#3251](https://github.com/open-telemetry/opentelemetry-python/pull/3251))
- Prometheus exporter support for auto instrumentation 
  ([#3413](https://github.com/open-telemetry/opentelemetry-python/pull/3413))
- Implement Process Resource detector
  ([#3472](https://github.com/open-telemetry/opentelemetry-python/pull/3472))


## Version 1.20.0/0.41b0 (2023-09-04)

- Modify Prometheus exporter to translate non-monotonic Sums into Gauges
  ([#3306](https://github.com/open-telemetry/opentelemetry-python/pull/3306))

## Version 1.19.0/0.40b0 (2023-07-13)

- Drop `setuptools` runtime requirement.
  ([#3372](https://github.com/open-telemetry/opentelemetry-python/pull/3372))
- Update the body type in the log
  ([$3343](https://github.com/open-telemetry/opentelemetry-python/pull/3343))
- Add max_scale option to Exponential Bucket Histogram Aggregation
  ([#3323](https://github.com/open-telemetry/opentelemetry-python/pull/3323))
- Use BoundedAttributes instead of raw dict to extract attributes from LogRecord
  ([#3310](https://github.com/open-telemetry/opentelemetry-python/pull/3310))
- Support dropped_attributes_count in LogRecord and exporters
  ([#3351](https://github.com/open-telemetry/opentelemetry-python/pull/3351))
- Add unit to view instrument selection criteria
  ([#3341](https://github.com/open-telemetry/opentelemetry-python/pull/3341))
- Upgrade opentelemetry-proto to 0.20 and regen
  [#3355](https://github.com/open-telemetry/opentelemetry-python/pull/3355))
- Include endpoint in Grpc transient error warning
  [#3362](https://github.com/open-telemetry/opentelemetry-python/pull/3362))
- Fixed bug where logging export is tracked as trace
  [#3375](https://github.com/open-telemetry/opentelemetry-python/pull/3375))
- Default LogRecord observed_timestamp to current timestamp
  [#3377](https://github.com/open-telemetry/opentelemetry-python/pull/3377))


## Version 1.18.0/0.39b0 (2023-05-19)

- Select histogram aggregation with an environment variable
  ([#3265](https://github.com/open-telemetry/opentelemetry-python/pull/3265))
- Move Protobuf encoding to its own package
  ([#3169](https://github.com/open-telemetry/opentelemetry-python/pull/3169))
- Add experimental feature to detect resource detectors in auto instrumentation
  ([#3181](https://github.com/open-telemetry/opentelemetry-python/pull/3181))
- Fix exporting of ExponentialBucketHistogramAggregation from opentelemetry.sdk.metrics.view
  ([#3240](https://github.com/open-telemetry/opentelemetry-python/pull/3240))
- Fix headers types mismatch for OTLP Exporters
  ([#3226](https://github.com/open-telemetry/opentelemetry-python/pull/3226))
- Fix suppress instrumentation for log batch processor
  ([#3223](https://github.com/open-telemetry/opentelemetry-python/pull/3223))
- Add speced out environment variables and arguments for BatchLogRecordProcessor
  ([#3237](https://github.com/open-telemetry/opentelemetry-python/pull/3237))
- Add benchmark tests for metrics
  ([#3267](https://github.com/open-telemetry/opentelemetry-python/pull/3267))


## Version 1.17.0/0.38b0 (2023-03-22)

- Implement LowMemory temporality
  ([#3223](https://github.com/open-telemetry/opentelemetry-python/pull/3223))
- PeriodicExportingMetricReader will continue if collection times out
  ([#3100](https://github.com/open-telemetry/opentelemetry-python/pull/3100))
- Fix formatting of ConsoleMetricExporter.
  ([#3197](https://github.com/open-telemetry/opentelemetry-python/pull/3197))
- Fix use of built-in samplers in SDK configuration
  ([#3176](https://github.com/open-telemetry/opentelemetry-python/pull/3176))
- Implement shutdown procedure forOTLP grpc exporters
  ([#3138](https://github.com/open-telemetry/opentelemetry-python/pull/3138))
- Add exponential histogram
  ([#2964](https://github.com/open-telemetry/opentelemetry-python/pull/2964))
- Add OpenCensus trace bridge/shim
  ([#3210](https://github.com/open-telemetry/opentelemetry-python/pull/3210))

## Version 1.16.0/0.37b0 (2023-02-17)

- Change ``__all__`` to be statically defined.
  ([#3143](https://github.com/open-telemetry/opentelemetry-python/pull/3143))
- Remove the ability to set a global metric prefix for Prometheus exporter
  ([#3137](https://github.com/open-telemetry/opentelemetry-python/pull/3137))
- Adds environment variables for log exporter
  ([#3037](https://github.com/open-telemetry/opentelemetry-python/pull/3037))
- Add attribute name to type warning message.
  ([3124](https://github.com/open-telemetry/opentelemetry-python/pull/3124))
- Add db metric name to semantic conventions
  ([#3115](https://github.com/open-telemetry/opentelemetry-python/pull/3115))
- Fix User-Agent header value for OTLP exporters to conform to RFC7231 & RFC7230
  ([#3128](https://github.com/open-telemetry/opentelemetry-python/pull/3128))
- Fix validation of baggage values
  ([#3058](https://github.com/open-telemetry/opentelemetry-python/pull/3058))
- Fix capitalization of baggage keys
  ([#3151](https://github.com/open-telemetry/opentelemetry-python/pull/3151))
- Bump min required api version for OTLP exporters
  ([#3156](https://github.com/open-telemetry/opentelemetry-python/pull/3156))
- deprecate jaeger exporters
  ([#3158](https://github.com/open-telemetry/opentelemetry-python/pull/3158))
- Create a single resource instance
  ([#3118](https://github.com/open-telemetry/opentelemetry-python/pull/3118))

## Version 1.15.0/0.36b0 (2022-12-09)

- PeriodicExportingMetricsReader with +Inf interval
  to support explicit metric collection
  ([#3059](https://github.com/open-telemetry/opentelemetry-python/pull/3059))
- Regenerate opentelemetry-proto to be compatible with protobuf 3 and 4
  ([#3070](https://github.com/open-telemetry/opentelemetry-python/pull/3070))
- Rename parse_headers to parse_env_headers and improve error message
  ([#2376](https://github.com/open-telemetry/opentelemetry-python/pull/2376))
- Add url decode values from OTEL_RESOURCE_ATTRIBUTES
  ([#3046](https://github.com/open-telemetry/opentelemetry-python/pull/3046))
- Fixed circular dependency issue with custom samplers
  ([#3026](https://github.com/open-telemetry/opentelemetry-python/pull/3026))
- Add missing entry points for OTLP/HTTP exporter
  ([#3027](https://github.com/open-telemetry/opentelemetry-python/pull/3027))
- Update logging to include logging api as per specification
  ([#3038](https://github.com/open-telemetry/opentelemetry-python/pull/3038))
- Fix: Avoid generator in metrics _ViewInstrumentMatch.collect()
  ([#3035](https://github.com/open-telemetry/opentelemetry-python/pull/3035)
- [exporter-otlp-proto-grpc] add user agent string
  ([#3009](https://github.com/open-telemetry/opentelemetry-python/pull/3009))

## Version 1.14.0/0.35b0 (2022-11-04)

- Add logarithm and exponent mappings
  ([#2960](https://github.com/open-telemetry/opentelemetry-python/pull/2960))
- Add and use missing metrics environment variables
  ([#2968](https://github.com/open-telemetry/opentelemetry-python/pull/2968))
- Enabled custom samplers via entry points
  ([#2972](https://github.com/open-telemetry/opentelemetry-python/pull/2972))
- Update log symbol names
  ([#2943](https://github.com/open-telemetry/opentelemetry-python/pull/2943))
- Update explicit histogram bucket boundaries
  ([#2947](https://github.com/open-telemetry/opentelemetry-python/pull/2947))
- `exporter-otlp-proto-http`: add user agent string
  ([#2959](https://github.com/open-telemetry/opentelemetry-python/pull/2959))
- Add http-metric instrument names to semantic conventions
  ([#2976](https://github.com/open-telemetry/opentelemetry-python/pull/2976))
- [exporter/opentelemetry-exporter-otlp-proto-http] Add OTLPMetricExporter
  ([#2891](https://github.com/open-telemetry/opentelemetry-python/pull/2891))
- Add support for py3.11
  ([#2997](https://github.com/open-telemetry/opentelemetry-python/pull/2997))
- Fix a bug with exporter retries for with newer versions of the backoff library
  ([#2980](https://github.com/open-telemetry/opentelemetry-python/pull/2980))

## Version 1.13.0/0.34b0 (2022-09-26)

- Add a configurable max_export_batch_size to the gRPC metrics exporter
  ([#2809](https://github.com/open-telemetry/opentelemetry-python/pull/2809))
- Remove support for 3.6
  ([#2763](https://github.com/open-telemetry/opentelemetry-python/pull/2763))
- Update PeriodicExportingMetricReader to never call export() concurrently
  ([#2873](https://github.com/open-telemetry/opentelemetry-python/pull/2873))
- Add param for `indent` size to `LogRecord.to_json()`
  ([#2870](https://github.com/open-telemetry/opentelemetry-python/pull/2870))
- Fix: Remove `LogEmitter.flush()` to align with OTel Log spec
  ([#2863](https://github.com/open-telemetry/opentelemetry-python/pull/2863))
- Bump minimum required API/SDK version for exporters that support metrics
  ([#2918](https://github.com/open-telemetry/opentelemetry-python/pull/2918))
- Fix metric reader examples + added `preferred_temporality` and `preferred_aggregation`
  for `ConsoleMetricExporter`
  ([#2911](https://github.com/open-telemetry/opentelemetry-python/pull/2911))
- Add support for setting OTLP export protocol with env vars, as defined in the
  [specifications](https://github.com/open-telemetry/opentelemetry-specification/blob/main/specification/protocol/exporter.md#specify-protocol)
  ([#2893](https://github.com/open-telemetry/opentelemetry-python/pull/2893))
- Add force_flush to span exporters
  ([#2919](https://github.com/open-telemetry/opentelemetry-python/pull/2919))

## Version 1.12.0/0.33b0 (2022-08-08)

- Add `force_flush` method to metrics exporter
  ([#2852](https://github.com/open-telemetry/opentelemetry-python/pull/2852))
- Change tracing to use `Resource.to_json()`
  ([#2784](https://github.com/open-telemetry/opentelemetry-python/pull/2784))
- Fix get_log_emitter instrumenting_module_version args typo
  ([#2830](https://github.com/open-telemetry/opentelemetry-python/pull/2830))
- Fix OTLP gRPC exporter warning message
  ([#2781](https://github.com/open-telemetry/opentelemetry-python/pull/2781))
- Fix tracing decorator with late configuration
  ([#2754](https://github.com/open-telemetry/opentelemetry-python/pull/2754))
- Fix --insecure of CLI argument
  ([#2696](https://github.com/open-telemetry/opentelemetry-python/pull/2696))
- Add temporality and aggregation configuration for metrics exporters,
  use `OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE` only for OTLP metrics exporter
  ([#2843](https://github.com/open-telemetry/opentelemetry-python/pull/2843))
- Instrument instances are always created through a Meter
  ([#2844](https://github.com/open-telemetry/opentelemetry-python/pull/2844))

## Version 1.12.0rc2/0.32b0 (2022-07-04)

- Fix instrument name and unit regexes
  ([#2796](https://github.com/open-telemetry/opentelemetry-python/pull/2796))
- Add optional sessions parameter to all Exporters leveraging requests.Session
  ([#2783](https://github.com/open-telemetry/opentelemetry-python/pull/2783)
- Add min/max fields to Histogram
  ([#2759](https://github.com/open-telemetry/opentelemetry-python/pull/2759))
- `opentelemetry-exporter-otlp-proto-http` Add support for OTLP/HTTP log exporter
  ([#2462](https://github.com/open-telemetry/opentelemetry-python/pull/2462))
- Fix yield of `None`-valued points
  ([#2745](https://github.com/open-telemetry/opentelemetry-python/pull/2745))
- Add missing `to_json` methods
  ([#2722](https://github.com/open-telemetry/opentelemetry-python/pull/2722)
- Fix type hints for textmap `Getter` and `Setter`
  ([#2657](https://github.com/open-telemetry/opentelemetry-python/pull/2657))
- Fix LogEmitterProvider.force_flush hanging randomly
  ([#2714](https://github.com/open-telemetry/opentelemetry-python/pull/2714))
- narrow protobuf dependencies to exclude protobuf >= 4
  ([#2720](https://github.com/open-telemetry/opentelemetry-python/pull/2720))
- Specify worker thread names
  ([#2724](https://github.com/open-telemetry/opentelemetry-python/pull/2724))
- Loosen dependency on `backoff` for newer Python versions
  ([#2726](https://github.com/open-telemetry/opentelemetry-python/pull/2726))
- fix: frozenset object has no attribute items
  ([#2727](https://github.com/open-telemetry/opentelemetry-python/pull/2727))
- fix: create suppress HTTP instrumentation key in opentelemetry context
  ([#2729](https://github.com/open-telemetry/opentelemetry-python/pull/2729))
- Support logs SDK auto instrumentation enable/disable with env
  ([#2728](https://github.com/open-telemetry/opentelemetry-python/pull/2728))
- fix: update entry point object references for metrics
  ([#2731](https://github.com/open-telemetry/opentelemetry-python/pull/2731))
- Allow set_status to accept the StatusCode and optional description
  ([#2735](https://github.com/open-telemetry/opentelemetry-python/pull/2735))
- Configure auto instrumentation to support metrics
  ([#2705](https://github.com/open-telemetry/opentelemetry-python/pull/2705))
- Add entrypoint for metrics exporter
  ([#2748](https://github.com/open-telemetry/opentelemetry-python/pull/2748))
- Fix Jaeger propagator usage with NonRecordingSpan
  ([#2762](https://github.com/open-telemetry/opentelemetry-python/pull/2762))
- Add `opentelemetry.propagate` module and `opentelemetry.propagators` package
  to the API reference documentation
  ([#2785](https://github.com/open-telemetry/opentelemetry-python/pull/2785))

## Version 1.12.0rc1/0.31b0 (2022-05-17)

- Fix LoggingHandler to handle LogRecord with exc_info=False
  ([#2690](https://github.com/open-telemetry/opentelemetry-python/pull/2690))
- Make metrics components public
  ([#2684](https://github.com/open-telemetry/opentelemetry-python/pull/2684))
- Update to semantic conventions v1.11.0
  ([#2669](https://github.com/open-telemetry/opentelemetry-python/pull/2669))
- Update opentelemetry-proto to v0.17.0
  ([#2668](https://github.com/open-telemetry/opentelemetry-python/pull/2668))
- Add CallbackOptions to observable instrument callback params
  ([#2664](https://github.com/open-telemetry/opentelemetry-python/pull/2664))
- Add timeouts to metric SDK
  ([#2653](https://github.com/open-telemetry/opentelemetry-python/pull/2653))
- Add variadic arguments to metric exporter/reader interfaces
  ([#2654](https://github.com/open-telemetry/opentelemetry-python/pull/2654))
- Added a `opentelemetry.sdk.resources.ProcessResourceDetector` that adds the
  'process.runtime.{name,version,description}' resource attributes when used
  with the `opentelemetry.sdk.resources.get_aggregated_resources` API
  ([#2660](https://github.com/open-telemetry/opentelemetry-python/pull/2660))
- Move Metrics API behind internal package
  ([#2651](https://github.com/open-telemetry/opentelemetry-python/pull/2651))

## Version 1.11.1/0.30b1 (2022-04-21)

- Add parameter to MetricReader constructor to select aggregation per instrument kind
  ([#2638](https://github.com/open-telemetry/opentelemetry-python/pull/2638))
- Add parameter to MetricReader constructor to select temporality per instrument kind
  ([#2637](https://github.com/open-telemetry/opentelemetry-python/pull/2637))
- Fix unhandled callback exceptions on async instruments
  ([#2614](https://github.com/open-telemetry/opentelemetry-python/pull/2614))
- Rename `DefaultCounter`, `DefaultHistogram`, `DefaultObservableCounter`,
  `DefaultObservableGauge`, `DefaultObservableUpDownCounter`, `DefaultUpDownCounter`
  instruments to `NoOpCounter`, `NoOpHistogram`, `NoOpObservableCounter`,
  `NoOpObservableGauge`, `NoOpObservableUpDownCounter`, `NoOpUpDownCounter`
  ([#2616](https://github.com/open-telemetry/opentelemetry-python/pull/2616))
- Deprecate InstrumentationLibraryInfo and Add InstrumentationScope
  ([#2583](https://github.com/open-telemetry/opentelemetry-python/pull/2583))

## Version 1.11.0/0.30b0 (2022-04-18)

- Rename API Measurement for async instruments to Observation
  ([#2617](https://github.com/open-telemetry/opentelemetry-python/pull/2617))
- Add support for zero or more callbacks
  ([#2602](https://github.com/open-telemetry/opentelemetry-python/pull/2602))
- Fix parsing of trace flags when extracting traceparent
  ([#2577](https://github.com/open-telemetry/opentelemetry-python/pull/2577))
- Add default aggregation
  ([#2543](https://github.com/open-telemetry/opentelemetry-python/pull/2543))
- Fix incorrect installation of some exporter “convenience” packages into
  “site-packages/src”
  ([#2525](https://github.com/open-telemetry/opentelemetry-python/pull/2525))
- Capture exception information as part of log attributes
  ([#2531](https://github.com/open-telemetry/opentelemetry-python/pull/2531))
- Change OTLPHandler to LoggingHandler
  ([#2528](https://github.com/open-telemetry/opentelemetry-python/pull/2528))
- Fix delta histogram sum not being reset on collection
  ([#2533](https://github.com/open-telemetry/opentelemetry-python/pull/2533))
- Add InMemoryMetricReader to metrics SDK
  ([#2540](https://github.com/open-telemetry/opentelemetry-python/pull/2540))
- Drop the usage of name field from log model in OTLP
  ([#2565](https://github.com/open-telemetry/opentelemetry-python/pull/2565))
- Update opentelemetry-proto to v0.15.0
  ([#2566](https://github.com/open-telemetry/opentelemetry-python/pull/2566))
- Remove `enable_default_view` option from sdk MeterProvider
  ([#2547](https://github.com/open-telemetry/opentelemetry-python/pull/2547))
- Update otlp-proto-grpc and otlp-proto-http exporters to have more lax requirements for `backoff` lib
  ([#2575](https://github.com/open-telemetry/opentelemetry-python/pull/2575))
- Add min/max to histogram point
  ([#2581](https://github.com/open-telemetry/opentelemetry-python/pull/2581))
- Update opentelemetry-proto to v0.16.0
  ([#2619](https://github.com/open-telemetry/opentelemetry-python/pull/2619))

## Version 1.10.0/0.29b0 (2022-03-10)

- Docs rework: [non-API docs are
  moving](https://github.com/open-telemetry/opentelemetry-python/issues/2172) to
  [opentelemetry.io](https://opentelemetry.io). For details, including a list of
  pages that have moved, see
  [#2453](https://github.com/open-telemetry/opentelemetry-python/pull/2453), and
  [#2498](https://github.com/open-telemetry/opentelemetry-python/pull/2498).
- `opentelemetry-exporter-otlp-proto-grpc` update SDK dependency to ~1.9.
  ([#2442](https://github.com/open-telemetry/opentelemetry-python/pull/2442))
- bugfix(auto-instrumentation): attach OTLPHandler to root logger
  ([#2450](https://github.com/open-telemetry/opentelemetry-python/pull/2450))
- Bump semantic conventions from 1.6.1 to 1.8.0
  ([#2461](https://github.com/open-telemetry/opentelemetry-python/pull/2461))
- fix exception handling in get_aggregated_resources
  ([#2464](https://github.com/open-telemetry/opentelemetry-python/pull/2464))
- Fix `OTEL_EXPORTER_OTLP_ENDPOINT` usage in OTLP HTTP trace exporter
  ([#2493](https://github.com/open-telemetry/opentelemetry-python/pull/2493))
- [exporter/opentelemetry-exporter-prometheus] restore package using the new metrics API
  ([#2321](https://github.com/open-telemetry/opentelemetry-python/pull/2321))

## Version 1.9.1/0.28b1 (2022-01-29)

- Update opentelemetry-proto to v0.12.0. Note that this update removes deprecated status codes.
  ([#2415](https://github.com/open-telemetry/opentelemetry-python/pull/2415))

## Version 1.9.0/0.28b0 (2022-01-26)

- Fix SpanLimits global span limit defaulting when set to 0
  ([#2398](https://github.com/open-telemetry/opentelemetry-python/pull/2398))
- Add Python version support policy
  ([#2397](https://github.com/open-telemetry/opentelemetry-python/pull/2397))
- Decode URL-encoded headers in environment variables
  ([#2312](https://github.com/open-telemetry/opentelemetry-python/pull/2312))
- [exporter/opentelemetry-exporter-otlp-proto-grpc] Add OTLPMetricExporter
  ([#2323](https://github.com/open-telemetry/opentelemetry-python/pull/2323))
- Complete metric exporter format and update OTLP exporter
  ([#2364](https://github.com/open-telemetry/opentelemetry-python/pull/2364))
- [api] Add `NoOpTracer` and `NoOpTracerProvider`. Marking `_DefaultTracer` and `_DefaultTracerProvider` as deprecated.
  ([#2363](https://github.com/open-telemetry/opentelemetry-python/pull/2363))
- [exporter/opentelemetry-exporter-otlp-proto-grpc] Add Sum to OTLPMetricExporter
  ([#2370](https://github.com/open-telemetry/opentelemetry-python/pull/2370))
- [api] Rename `_DefaultMeter` and `_DefaultMeterProvider` to `NoOpMeter` and `NoOpMeterProvider`.
  ([#2383](https://github.com/open-telemetry/opentelemetry-python/pull/2383))
- [exporter/opentelemetry-exporter-otlp-proto-grpc] Add Gauge to OTLPMetricExporter
  ([#2408](https://github.com/open-telemetry/opentelemetry-python/pull/2408))
- [logs] prevent None from causing problems
  ([#2410](https://github.com/open-telemetry/opentelemetry-python/pull/2410))

## Version 1.8.0/0.27b0 (2021-12-17)

- Adds Aggregation and instruments as part of Metrics SDK
  ([#2234](https://github.com/open-telemetry/opentelemetry-python/pull/2234))
- Update visibility of OTEL_METRICS_EXPORTER environment variable
  ([#2303](https://github.com/open-telemetry/opentelemetry-python/pull/2303))
- Adding entrypoints for log emitter provider and console, otlp log exporters
  ([#2253](https://github.com/open-telemetry/opentelemetry-python/pull/2253))
- Rename ConsoleExporter to ConsoleLogExporter
  ([#2307](https://github.com/open-telemetry/opentelemetry-python/pull/2307))
- Adding OTEL_LOGS_EXPORTER environment variable
  ([#2320](https://github.com/open-telemetry/opentelemetry-python/pull/2320))
- Add `setuptools` to `install_requires`
  ([#2334](https://github.com/open-telemetry/opentelemetry-python/pull/2334))
- Add otlp entrypoint for log exporter
  ([#2322](https://github.com/open-telemetry/opentelemetry-python/pull/2322))
- Support insecure configuration for OTLP gRPC exporter
  ([#2350](https://github.com/open-telemetry/opentelemetry-python/pull/2350))

## Version 1.7.1/0.26b1 (2021-11-11)

- Add support for Python 3.10
  ([#2207](https://github.com/open-telemetry/opentelemetry-python/pull/2207))
- remove `X-B3-ParentSpanId` for B3 propagator as per OpenTelemetry specification
  ([#2237](https://github.com/open-telemetry/opentelemetry-python/pull/2237))
- Populate `auto.version` in Resource if using auto-instrumentation
  ([#2243](https://github.com/open-telemetry/opentelemetry-python/pull/2243))
- Return proxy instruments from ProxyMeter
  ([#2169](https://github.com/open-telemetry/opentelemetry-python/pull/2169))
- Make Measurement a concrete class
  ([#2153](https://github.com/open-telemetry/opentelemetry-python/pull/2153))
- Add metrics API
  ([#1887](https://github.com/open-telemetry/opentelemetry-python/pull/1887))
- Make batch processor fork aware and reinit when needed
  ([#2242](https://github.com/open-telemetry/opentelemetry-python/pull/2242))
- `opentelemetry-sdk` Sanitize env var resource attribute pairs
  ([#2256](https://github.com/open-telemetry/opentelemetry-python/pull/2256))
- `opentelemetry-test` start releasing to pypi.org
  ([#2269](https://github.com/open-telemetry/opentelemetry-python/pull/2269))

## Version 1.6.2/0.25b2 (2021-10-19)

- Fix parental trace relationship for opentracing `follows_from` reference
  ([#2180](https://github.com/open-telemetry/opentelemetry-python/pull/2180))

## Version 1.6.1/0.25b1 (2021-10-18)

- Fix ReadableSpan property types attempting to create a mapping from a list
  ([#2215](https://github.com/open-telemetry/opentelemetry-python/pull/2215))
- Upgrade GRPC/protobuf related dependency and regenerate otlp protobufs
  ([#2201](https://github.com/open-telemetry/opentelemetry-python/pull/2201))
- Propagation: only warn about oversized baggage headers when headers exist
  ([#2212](https://github.com/open-telemetry/opentelemetry-python/pull/2212))

## Version 1.6.0/0.25b0 (2021-10-13)

- Fix race in `set_tracer_provider()`
  ([#2182](https://github.com/open-telemetry/opentelemetry-python/pull/2182))
- Automatically load OTEL environment variables as options for `opentelemetry-instrument`
  ([#1969](https://github.com/open-telemetry/opentelemetry-python/pull/1969))
- `opentelemetry-semantic-conventions` Update to semantic conventions v1.6.1
  ([#2077](https://github.com/open-telemetry/opentelemetry-python/pull/2077))
- Do not count invalid attributes for dropped
  ([#2096](https://github.com/open-telemetry/opentelemetry-python/pull/2096))
- Fix propagation bug caused by counting skipped entries
  ([#2071](https://github.com/open-telemetry/opentelemetry-python/pull/2071))
- Add entry point for exporters with default protocol
  ([#2093](https://github.com/open-telemetry/opentelemetry-python/pull/2093))
- Renamed entrypoints `otlp_proto_http_span`, `otlp_proto_grpc_span`, `console_span` to remove
  redundant `_span` suffix.
  ([#2093](https://github.com/open-telemetry/opentelemetry-python/pull/2093))
- Do not skip sequence attribute on decode error
  ([#2097](https://github.com/open-telemetry/opentelemetry-python/pull/2097))
- `opentelemetry-test`: Add `HttpTestBase` to allow tests with actual TCP sockets
  ([#2101](https://github.com/open-telemetry/opentelemetry-python/pull/2101))
- Fix incorrect headers parsing via environment variables
  ([#2103](https://github.com/open-telemetry/opentelemetry-python/pull/2103))
- Add support for OTEL_ATTRIBUTE_COUNT_LIMIT
  ([#2139](https://github.com/open-telemetry/opentelemetry-python/pull/2139))
- Attribute limits no longer apply to Resource attributes
  ([#2138](https://github.com/open-telemetry/opentelemetry-python/pull/2138))
- `opentelemetry-exporter-otlp`: Add `opentelemetry-otlp-proto-http` as dependency
  ([#2147](https://github.com/open-telemetry/opentelemetry-python/pull/2147))
- Fix validity calculation for trace and span IDs
  ([#2145](https://github.com/open-telemetry/opentelemetry-python/pull/2145))
- Add `schema_url` to `TracerProvider.get_tracer`
  ([#2154](https://github.com/open-telemetry/opentelemetry-python/pull/2154))
- Make baggage implementation w3c spec complaint
  ([#2167](https://github.com/open-telemetry/opentelemetry-python/pull/2167))
- Add name to `BatchSpanProcessor` worker thread
  ([#2186](https://github.com/open-telemetry/opentelemetry-python/pull/2186))

## Version 1.5.0/0.24b0 (2021-08-26)

- Add pre and post instrumentation entry points
  ([#1983](https://github.com/open-telemetry/opentelemetry-python/pull/1983))
- Fix documentation on well known exporters and variable OTEL_TRACES_EXPORTER which were misnamed
  ([#2023](https://github.com/open-telemetry/opentelemetry-python/pull/2023))
- `opentelemetry-sdk` `get_aggregated_resource()` returns default resource and service name
  whenever called
  ([#2013](https://github.com/open-telemetry/opentelemetry-python/pull/2013))
- `opentelemetry-distro` & `opentelemetry-sdk` Moved Auto Instrumentation Configurator code to SDK
  to let distros use its default implementation
  ([#1937](https://github.com/open-telemetry/opentelemetry-python/pull/1937))
- Add Trace ID validation to
  meet [TraceID spec](https://github.com/open-telemetry/opentelemetry-specification/blob/main/specification/overview.md#spancontext) ([#1992](https://github.com/open-telemetry/opentelemetry-python/pull/1992))
- Fixed Python 3.10 incompatibility in `opentelemetry-opentracing-shim` tests
  ([#2018](https://github.com/open-telemetry/opentelemetry-python/pull/2018))
- `opentelemetry-sdk` added support for `OTEL_SPAN_ATTRIBUTE_VALUE_LENGTH_LIMIT`
  ([#2044](https://github.com/open-telemetry/opentelemetry-python/pull/2044))
- `opentelemetry-sdk` Fixed bugs (#2041, #2042 & #2045) in Span Limits
  ([#2044](https://github.com/open-telemetry/opentelemetry-python/pull/2044))
- `opentelemetry-sdk` Add support for `OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT` env var
  ([#2056](https://github.com/open-telemetry/opentelemetry-python/pull/2056))
- `opentelemetry-sdk` Treat limit even vars set to empty values as unset/unlimited.
  ([#2054](https://github.com/open-telemetry/opentelemetry-python/pull/2054))
- `opentelemetry-api` Attribute keys must be non-empty strings.
  ([#2057](https://github.com/open-telemetry/opentelemetry-python/pull/2057))

## Version 0.23.1 (2021-07-26)

### Changed

- Fix opentelemetry-bootstrap dependency script.
  ([#1987](https://github.com/open-telemetry/opentelemetry-python/pull/1987))

## Version 1.4.0/0.23b0 (2021-07-21)

### Added

- Moved `opentelemetry-instrumentation` to core repository.
  ([#1959](https://github.com/open-telemetry/opentelemetry-python/pull/1959))
- Add support for OTLP Exporter Protobuf over HTTP
  ([#1868](https://github.com/open-telemetry/opentelemetry-python/pull/1868))
- Dropped attributes/events/links count available exposed on ReadableSpans.
  ([#1893](https://github.com/open-telemetry/opentelemetry-python/pull/1893))
- Added dropped count to otlp, jaeger and zipkin exporters.
  ([#1893](https://github.com/open-telemetry/opentelemetry-python/pull/1893))

### Added

- Give OTLPHandler the ability to process attributes
  ([#1952](https://github.com/open-telemetry/opentelemetry-python/pull/1952))
- Add global LogEmitterProvider and convenience function get_log_emitter
  ([#1901](https://github.com/open-telemetry/opentelemetry-python/pull/1901))
- Add OTLPHandler for standard library logging module
  ([#1903](https://github.com/open-telemetry/opentelemetry-python/pull/1903))

### Changed

- Updated `opentelemetry-opencensus-exporter` to use `service_name` of spans instead of resource
  ([#1897](https://github.com/open-telemetry/opentelemetry-python/pull/1897))
- Added descriptions to the env variables mentioned in the opentelemetry-specification
  ([#1898](https://github.com/open-telemetry/opentelemetry-python/pull/1898))
- Ignore calls to `Span.set_status` with `StatusCode.UNSET` and also if previous status already
  had `StatusCode.OK`.
  ([#1902](https://github.com/open-telemetry/opentelemetry-python/pull/1902))
- Attributes for `Link` and `Resource` are immutable as they are for `Event`, which means
  any attempt to modify attributes directly will result in a `TypeError` exception.
  ([#1909](https://github.com/open-telemetry/opentelemetry-python/pull/1909))
- Added `BoundedAttributes` to the API to make it available for `Link` which is defined in the
  API. Marked `BoundedDict` in the SDK as deprecated as a result.
  ([#1915](https://github.com/open-telemetry/opentelemetry-python/pull/1915))
- Fix OTLP SpanExporter to distinguish spans based off Resource and InstrumentationInfo
  ([#1927](https://github.com/open-telemetry/opentelemetry-python/pull/1927))
- Updating dependency for opentelemetry api/sdk packages to support major version instead of
  pinning to specific versions.
  ([#1933](https://github.com/open-telemetry/opentelemetry-python/pull/1933))
- `opentelemetry-semantic-conventions` Generate semconv constants update for OTel Spec 1.5.0
  ([#1946](https://github.com/open-telemetry/opentelemetry-python/pull/1946))

### Fixed

- Updated `opentelementry-opentracing-shim` `ScopeShim` to report exceptions in
  opentelemetry specification format, rather than opentracing spec format.
  ([#1878](https://github.com/open-telemetry/opentelemetry-python/pull/1878))

## Version 1.3.0/0.22b0 (2021-06-01)

### Added

- Allow span limits to be set programmatically via TracerProvider.
  ([#1877](https://github.com/open-telemetry/opentelemetry-python/pull/1877))
- Added support for CreateKey functionality.
  ([#1853](https://github.com/open-telemetry/opentelemetry-python/pull/1853))

### Changed

- Updated get_tracer to return an empty string when passed an invalid name
  ([#1854](https://github.com/open-telemetry/opentelemetry-python/pull/1854))
- Changed AttributeValue sequences to warn mypy users on adding None values to array
  ([#1855](https://github.com/open-telemetry/opentelemetry-python/pull/1855))
- Fixed exporter OTLP header parsing to match baggage header formatting.
  ([#1869](https://github.com/open-telemetry/opentelemetry-python/pull/1869))
- Added optional `schema_url` field to `Resource` class
  ([#1871](https://github.com/open-telemetry/opentelemetry-python/pull/1871))
- Update protos to latest version release 0.9.0
  ([#1873](https://github.com/open-telemetry/opentelemetry-python/pull/1873))

## Version 1.2.0/0.21b0 (2021-05-11)

### Added

- Added example for running Django with auto instrumentation.
  ([#1803](https://github.com/open-telemetry/opentelemetry-python/pull/1803))
- Added `B3SingleFormat` and `B3MultiFormat` propagators to the `opentelemetry-propagator-b3` package.
  ([#1823](https://github.com/open-telemetry/opentelemetry-python/pull/1823))
- Added support for OTEL_SERVICE_NAME.
  ([#1829](https://github.com/open-telemetry/opentelemetry-python/pull/1829))
- Lazily read/configure limits and allow limits to be unset.
  ([#1839](https://github.com/open-telemetry/opentelemetry-python/pull/1839))
- Added support for OTEL_EXPORTER_JAEGER_TIMEOUT
  ([#1863](https://github.com/open-telemetry/opentelemetry-python/pull/1863))

### Changed

- Fixed OTLP gRPC exporter silently failing if scheme is not specified in endpoint.
  ([#1806](https://github.com/open-telemetry/opentelemetry-python/pull/1806))
- Rename CompositeHTTPPropagator to CompositePropagator as per specification.
  ([#1807](https://github.com/open-telemetry/opentelemetry-python/pull/1807))
- Propagators use the root context as default for `extract` and do not modify
  the context if extracting from carrier does not work.
  ([#1811](https://github.com/open-telemetry/opentelemetry-python/pull/1811))
- Fixed `b3` propagator entrypoint to point to `B3SingleFormat` propagator.
  ([#1823](https://github.com/open-telemetry/opentelemetry-python/pull/1823))
- Added `b3multi` propagator entrypoint to point to `B3MultiFormat` propagator.
  ([#1823](https://github.com/open-telemetry/opentelemetry-python/pull/1823))
- Improve warning when failing to decode byte attribute
  ([#1810](https://github.com/open-telemetry/opentelemetry-python/pull/1810))
- Fixed inconsistency in parent_id formatting from the ConsoleSpanExporter
  ([#1833](https://github.com/open-telemetry/opentelemetry-python/pull/1833))
- Include span parent in Jaeger gRPC export as `CHILD_OF` reference
  ([#1809])(https://github.com/open-telemetry/opentelemetry-python/pull/1809)
- Fixed sequence values in OTLP exporter not translating
  ([#1818](https://github.com/open-telemetry/opentelemetry-python/pull/1818))
- Update transient errors retry timeout and retryable status codes
  ([#1842](https://github.com/open-telemetry/opentelemetry-python/pull/1842))
- Apply validation of attributes to `Resource`, move attribute related logic to separate package.
  ([#1834](https://github.com/open-telemetry/opentelemetry-python/pull/1834))
- Fix start span behavior when excess links and attributes are included
  ([#1856](https://github.com/open-telemetry/opentelemetry-python/pull/1856))

### Removed

- Moved `opentelemetry-instrumentation` to contrib repository.
  ([#1797](https://github.com/open-telemetry/opentelemetry-python/pull/1797))

## Version 1.1.0 (2021-04-20)

### Added

- Added `py.typed` file to every package. This should resolve a bunch of mypy
  errors for users.
  ([#1720](https://github.com/open-telemetry/opentelemetry-python/pull/1720))
- Add auto generated trace and resource attributes semantic conventions
  ([#1759](https://github.com/open-telemetry/opentelemetry-python/pull/1759))
- Added `SpanKind` to `should_sample` parameters, suggest using parent span context's tracestate
  instead of manually passed in tracestate in `should_sample`
  ([#1764](https://github.com/open-telemetry/opentelemetry-python/pull/1764))
- Added experimental HTTP back propagators.
  ([#1762](https://github.com/open-telemetry/opentelemetry-python/pull/1762))
- Zipkin exporter: Add support for timeout and implement shutdown
  ([#1799](https://github.com/open-telemetry/opentelemetry-python/pull/1799))

### Changed

- Adjust `B3Format` propagator to be spec compliant by not modifying context
  when propagation headers are not present/invalid/empty
  ([#1728](https://github.com/open-telemetry/opentelemetry-python/pull/1728))
- Silence unnecessary warning when creating a new Status object without description.
  ([#1721](https://github.com/open-telemetry/opentelemetry-python/pull/1721))
- Update bootstrap cmd to use exact version when installing instrumentation packages.
  ([#1722](https://github.com/open-telemetry/opentelemetry-python/pull/1722))
- Fix B3 propagator to never return None.
  ([#1750](https://github.com/open-telemetry/opentelemetry-python/pull/1750))
- Added ProxyTracerProvider and ProxyTracer implementations to allow fetching provider
  and tracer instances before a global provider is set up.
  ([#1726](https://github.com/open-telemetry/opentelemetry-python/pull/1726))
- Added `__contains__` to `opentelementry.trace.span.TraceState`.
  ([#1773](https://github.com/open-telemetry/opentelemetry-python/pull/1773))
- `opentelemetry-opentracing-shim` Fix an issue in the shim where a Span was being wrapped
  in a NonRecordingSpan when it wasn't necessary.
  ([#1776](https://github.com/open-telemetry/opentelemetry-python/pull/1776))
- OTLP Exporter now uses the scheme in the endpoint to determine whether to establish
  a secure connection or not.
  ([#1771](https://github.com/open-telemetry/opentelemetry-python/pull/1771))

## Version 1.0.0 (2021-03-26)

### Added

- Document how to work with fork process web server models(Gunicorn, uWSGI etc...)
  ([#1609](https://github.com/open-telemetry/opentelemetry-python/pull/1609))
- Add `max_attr_value_length` support to Jaeger exporter
  ([#1633](https://github.com/open-telemetry/opentelemetry-python/pull/1633))
- Moved `use_span` from Tracer to `opentelemetry.trace.use_span`.
  ([#1668](https://github.com/open-telemetry/opentelemetry-python/pull/1668))
- `opentelemetry.trace.use_span()` will now overwrite previously set status on span in case an
  exception is raised inside the context manager and `set_status_on_exception` is set to `True`.
  ([#1668](https://github.com/open-telemetry/opentelemetry-python/pull/1668))
- Add `udp_split_oversized_batches` support to jaeger exporter
  ([#1500](https://github.com/open-telemetry/opentelemetry-python/pull/1500))

### Changed

- remove `service_name` from constructor of jaeger and opencensus exporters and
  use of env variable `OTEL_PYTHON_SERVICE_NAME`
  ([#1669])(https://github.com/open-telemetry/opentelemetry-python/pull/1669)
- Rename `IdsGenerator` to `IdGenerator`
  ([#1651](https://github.com/open-telemetry/opentelemetry-python/pull/1651))
- Make TracerProvider's resource attribute private
  ([#1652](https://github.com/open-telemetry/opentelemetry-python/pull/1652))
- Rename Resource's `create_empty` to `get_empty`
  ([#1653](https://github.com/open-telemetry/opentelemetry-python/pull/1653))
- Renamed `BatchExportSpanProcessor` to `BatchSpanProcessor` and `SimpleExportSpanProcessor` to
  `SimpleSpanProcessor`
  ([#1656](https://github.com/open-telemetry/opentelemetry-python/pull/1656))
- Rename `DefaultSpan` to `NonRecordingSpan`
  ([#1661](https://github.com/open-telemetry/opentelemetry-python/pull/1661))
- Fixed distro configuration with `OTEL_TRACES_EXPORTER` env var set to `otlp`
  ([#1657](https://github.com/open-telemetry/opentelemetry-python/pull/1657))
- Moving `Getter`, `Setter` and `TextMapPropagator` out of `opentelemetry.trace.propagation` and
  into `opentelemetry.propagators`
  ([#1662](https://github.com/open-telemetry/opentelemetry-python/pull/1662))
- Rename `BaggagePropagator` to `W3CBaggagePropagator`
  ([#1663](https://github.com/open-telemetry/opentelemetry-python/pull/1663))
- Rename `JaegerSpanExporter` to `JaegerExporter` and rename `ZipkinSpanExporter` to `ZipkinExporter`
  ([#1664](https://github.com/open-telemetry/opentelemetry-python/pull/1664))
- Expose `StatusCode` from the `opentelemetry.trace` module
  ([#1681](https://github.com/open-telemetry/opentelemetry-python/pull/1681))
- Status now only sets `description` when `status_code` is set to `StatusCode.ERROR`
  ([#1673](https://github.com/open-telemetry/opentelemetry-python/pull/1673))
- Update OTLP exporter to use OTLP proto `0.7.0`
  ([#1674](https://github.com/open-telemetry/opentelemetry-python/pull/1674))
- Remove time_ns from API and add a warning for older versions of Python
  ([#1602](https://github.com/open-telemetry/opentelemetry-python/pull/1602))
- Hide implementation classes/variables in api/sdk
  ([#1684](https://github.com/open-telemetry/opentelemetry-python/pull/1684))
- Cleanup OTLP exporter compression options, add tests
  ([#1671](https://github.com/open-telemetry/opentelemetry-python/pull/1671))
- Initial documentation for environment variables
  ([#1680](https://github.com/open-telemetry/opentelemetry-python/pull/1680))
- Change Zipkin exporter to obtain service.name from span
  ([#1696](https://github.com/open-telemetry/opentelemetry-python/pull/1696))
- Split up `opentelemetry-exporter-jaeger` package into `opentelemetry-exporter-jaeger-proto-grpc` and
  `opentelemetry-exporter-jaeger-thrift` packages to reduce dependencies for each one.
  ([#1694](https://github.com/open-telemetry/opentelemetry-python/pull/1694))
- Added `opentelemetry-exporter-otlp-proto-grpc` and changed `opentelemetry-exporter-otlp` to
  install it as a dependency. This will allow for the next package/protocol to also be in
  its own package.
  ([#1695](https://github.com/open-telemetry/opentelemetry-python/pull/1695))
- Change Jaeger exporters to obtain service.name from span
  ([#1703](https://github.com/open-telemetry/opentelemetry-python/pull/1703))
- Fixed an unset `OTEL_TRACES_EXPORTER` resulting in an error
  ([#1707](https://github.com/open-telemetry/opentelemetry-python/pull/1707))
- Split Zipkin exporter into `opentelemetry-exporter-zipkin-json` and
  `opentelemetry-exporter-zipkin-proto-http` packages to reduce dependencies. The
  `opentelemetry-exporter-zipkin` installs both.
  ([#1699](https://github.com/open-telemetry/opentelemetry-python/pull/1699))
- Make setters and getters optional
  ([#1690](https://github.com/open-telemetry/opentelemetry-python/pull/1690))

### Removed

- Removed unused `get_hexadecimal_trace_id` and `get_hexadecimal_span_id` methods.
  ([#1675](https://github.com/open-telemetry/opentelemetry-python/pull/1675))
- Remove `OTEL_EXPORTER_*_ INSECURE` env var
  ([#1682](https://github.com/open-telemetry/opentelemetry-python/pull/1682))
- Removing support for Python 3.5
  ([#1706](https://github.com/open-telemetry/opentelemetry-python/pull/1706))

## Version 0.19b0 (2021-03-26)

### Changed

- remove `service_name` from constructor of jaeger and opencensus exporters and
  use of env variable `OTEL_PYTHON_SERVICE_NAME`
  ([#1669])(https://github.com/open-telemetry/opentelemetry-python/pull/1669)
- Rename `IdsGenerator` to `IdGenerator`
  ([#1651](https://github.com/open-telemetry/opentelemetry-python/pull/1651))
>>>>>>> upstream/main

### Removed

- Removing support for Python 3.5
<<<<<<< HEAD
  ([#374](https://github.com/open-telemetry/opentelemetry-python/pull/374))
=======
  ([#1706](https://github.com/open-telemetry/opentelemetry-python/pull/1706))
>>>>>>> upstream/main

## Version 0.18b0 (2021-02-16)

### Added

<<<<<<< HEAD
- `opentelemetry-propagator-ot-trace` Add OT Trace Propagator
  ([#302](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/302))
- `opentelemetry-instrumentation-logging` Added logging instrumentation to enable log - trace correlation.
  ([#345](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/345))

### Removed

- Remove `component` span attribute in instrumentations.
  `opentelemetry-instrumentation-aiopg`, `opentelemetry-instrumentation-dbapi` Remove unused `database_type` parameter from `trace_integration` function.
  ([#301](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/301))
- `opentelemetry-instrumentation-asgi` Return header values using case insensitive keys
  ([#308](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/308))
- Remove metrics from all instrumentations
  ([#312](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/312))
- `opentelemetry-instrumentation-boto` updated to set span attributes instead of overriding the resource.
  ([#310](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/310))
- `opentelemetry-instrumentation-grpc` Fix issue tracking child spans in streaming responses
  ([#260](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/260))
- `opentelemetry-instrumentation-grpc` Updated client attributes, added tests, fixed examples, docs
  ([#269](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/269))
=======
- Add urllib to opentelemetry-bootstrap target list
  ([#1584](https://github.com/open-telemetry/opentelemetry-python/pull/1584))

## Version 1.0.0rc1 (2021-02-12)

### Changed

- Tracer provider environment variables are now consistent with the rest
  ([#1571](https://github.com/open-telemetry/opentelemetry-python/pull/1571))
- Rename `TRACE_` to `TRACES_` for environment variables
  ([#1595](https://github.com/open-telemetry/opentelemetry-python/pull/1595))
- Limits for Span attributes, events and links have been updated to 128
  ([1597](https://github.com/open-telemetry/opentelemetry-python/pull/1597))
- Read-only Span attributes have been moved to ReadableSpan class
  ([#1560](https://github.com/open-telemetry/opentelemetry-python/pull/1560))
- `BatchExportSpanProcessor` flushes export queue when it reaches `max_export_batch_size`
  ([#1521](https://github.com/open-telemetry/opentelemetry-python/pull/1521))

### Added

- Added `end_on_exit` argument to `start_as_current_span`
  ([#1519](https://github.com/open-telemetry/opentelemetry-python/pull/1519))
- Add `Span.set_attributes` method to set multiple values with one call
  ([#1520](https://github.com/open-telemetry/opentelemetry-python/pull/1520))
- Make sure Resources follow semantic conventions
  ([#1480](https://github.com/open-telemetry/opentelemetry-python/pull/1480))
- Allow missing carrier headers to continue without raising AttributeError
  ([#1545](https://github.com/open-telemetry/opentelemetry-python/pull/1545))

### Removed

- Remove Configuration
  ([#1523](https://github.com/open-telemetry/opentelemetry-python/pull/1523))
- Remove Metrics as part of stable, marked as experimental
  ([#1568](https://github.com/open-telemetry/opentelemetry-python/pull/1568))
>>>>>>> upstream/main

## Version 0.17b0 (2021-01-20)

### Added

<<<<<<< HEAD
- `opentelemetry-instrumentation-sqlalchemy` Ensure spans have kind set to "CLIENT"
  ([#278](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/278))
- `opentelemetry-instrumentation-celery` Add support for Celery version 5.x
  ([#266](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/266))
- `opentelemetry-instrumentation-urllib` Add urllib instrumentation
  ([#222](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/222))
- `opentelemetry-exporter-datadog` Add fields method
  ([#226](https://github.com/open-telemetry/opentelemetry-python/pull/226))
- `opentelemetry-sdk-extension-aws` Add method to return fields injected by propagator
  ([#226](https://github.com/open-telemetry/opentelemetry-python/pull/226))
- `opentelemetry-exporter-prometheus-remote-write` Prometheus Remote Write Exporter Setup
  ([#180](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/180))
- `opentelemetry-exporter-prometheus-remote-write` Add Exporter constructor validation methods in Prometheus Remote Write Exporter
  ([#206](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/206))
- `opentelemetry-exporter-prometheus-remote-write` Add conversion to TimeSeries methods in Prometheus Remote Write Exporter
  ([#207](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/207))
- `opentelemetry-exporter-prometheus-remote-write` Add request methods to Prometheus Remote Write Exporter
  ([#212](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/212))
- `opentelemetry-instrumentation-fastapi` Added support for excluding some routes with env var `OTEL_PYTHON_FASTAPI_EXCLUDED_URLS`
  ([#237](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/237))
- `opentelemetry-instrumentation-starlette` Added support for excluding some routes with env var `OTEL_PYTHON_STARLETTE_EXCLUDED_URLS`
  ([#237](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/237))
- Add Prometheus Remote Write Exporter integration tests in opentelemetry-docker-tests
  ([#216](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/216))
- `opentelemetry-instrumentation-grpc` Add tests for grpc span attributes, grpc `abort()` conditions
  ([#236](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/236))
- Add README and example app for Prometheus Remote Write Exporter
  ([#227](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/227]))
- `opentelemetry-instrumentation-botocore` Adds a field to report the number of retries it take to complete an API call
  ([#275](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/275))
- `opentelemetry-instrumentation-requests` Use instanceof to check if responses are valid Response objects
  ([#273](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/273))

### Changed

- Fix broken links to project ([#413](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/413))
- `opentelemetry-instrumentation-asgi`, `opentelemetry-instrumentation-wsgi` Return `None` for `CarrierGetter` if key not found
  ([#233](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/233))
- `opentelemetry-instrumentation-grpc` Comply with updated spec, rework tests
  ([#236](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/236))
- `opentelemetry-instrumentation-asgi`, `opentelemetry-instrumentation-falcon`, `opentelemetry-instrumentation-flask`, `opentelemetry-instrumentation-pyramid`, `opentelemetry-instrumentation-wsgi` Renamed `host.port` attribute to `net.host.port`
  ([#242](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/242))
- `opentelemetry-instrumentation-flask` Do not emit a warning message for request contexts created with `app.test_request_context`
  ([#253](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/253))
- `opentelemetry-instrumentation-requests`, `opentelemetry-instrumentation-urllib` Fix span name callback parameters
  ([#259](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/259))
- `opentelemetry-exporter-datadog` Fix unintentional type change of span trace flags
  ([#261](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/261))
- `opentelemetry-instrumentation-aiopg` Fix AttributeError `__aexit__` when `aiopg.connect` and `aio[g].create_pool` used with async context manager
  ([#235](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/235))
- `opentelemetry-exporter-datadog` `opentelemetry-sdk-extension-aws` Fix reference to ids_generator in sdk
  ([#283](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/283))
- `opentelemetry-instrumentation-sqlalchemy` Use SQL operation and DB name as span name.
  ([#254](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/254))
- `opentelemetry-instrumentation-dbapi`, `TracedCursor` replaced by `CursorTracer`
  ([#246](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/246))
- `opentelemetry-instrumentation-psycopg2`, Added support for psycopg2 registered types.
  ([#246](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/246))
- `opentelemetry-instrumentation-dbapi`, `opentelemetry-instrumentation-psycopg2`, `opentelemetry-instrumentation-mysql`, `opentelemetry-instrumentation-pymysql`, `opentelemetry-instrumentation-aiopg` Use SQL command name as the span operation name instead of the entire query.
  ([#246](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/246))
- Update TraceState to adhere to specs
  ([#276](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/276))

### Removed

- Remove Configuration
  ([#285](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/285))

## Version 0.16b1 (2020-11-26)

=======
- Add support for OTLP v0.6.0
  ([#1472](https://github.com/open-telemetry/opentelemetry-python/pull/1472))
- Add protobuf via gRPC exporting support for Jaeger
  ([#1471](https://github.com/open-telemetry/opentelemetry-python/pull/1471))
- Add support for Python 3.9
  ([#1441](https://github.com/open-telemetry/opentelemetry-python/pull/1441))
- Added the ability to disable instrumenting libraries specified by OTEL_PYTHON_DISABLED_INSTRUMENTATIONS env variable,
  when using opentelemetry-instrument command.
  ([#1461](https://github.com/open-telemetry/opentelemetry-python/pull/1461))
- Add `fields` to propagators
  ([#1374](https://github.com/open-telemetry/opentelemetry-python/pull/1374))
- Add local/remote samplers to parent based sampler
  ([#1440](https://github.com/open-telemetry/opentelemetry-python/pull/1440))
- Add support for OTEL*SPAN*{ATTRIBUTE_COUNT_LIMIT,EVENT_COUNT_LIMIT,LINK_COUNT_LIMIT}
  ([#1377](https://github.com/open-telemetry/opentelemetry-python/pull/1377))
- Return `None` for `DictGetter` if key not found
  ([#1449](https://github.com/open-telemetry/opentelemetry-python/pull/1449))
- Added support for Jaeger propagator
  ([#1219](https://github.com/open-telemetry/opentelemetry-python/pull/1219))
- Remove dependency on SDK from `opentelemetry-instrumentation` package. The
  `opentelemetry-sdk` package now registers an entrypoint `opentelemetry_configurator`
  to allow `opentelemetry-instrument` to load the configuration for the SDK
  ([#1420](https://github.com/open-telemetry/opentelemetry-python/pull/1420))
- `opentelemetry-exporter-zipkin` Add support for array attributes in Span and Resource exports
  ([#1285](https://github.com/open-telemetry/opentelemetry-python/pull/1285))
- Added `__repr__` for `DefaultSpan`, added `trace_flags` to `__repr__` of
  `SpanContext` ([#1485](https://github.com/open-telemetry/opentelemetry-python/pull/1485))
- `opentelemetry-sdk` Add support for OTEL_TRACE_SAMPLER and OTEL_TRACE_SAMPLER_ARG env variables
  ([#1496](https://github.com/open-telemetry/opentelemetry-python/pull/1496))
- Adding `opentelemetry-distro` package to add default configuration for
  span exporter to OTLP
  ([#1482](https://github.com/open-telemetry/opentelemetry-python/pull/1482))

### Changed

- `opentelemetry-exporter-zipkin` Updated zipkin exporter status code and error tag
  ([#1486](https://github.com/open-telemetry/opentelemetry-python/pull/1486))
- Recreate span on every run of a `start_as_current_span`-decorated function
  ([#1451](https://github.com/open-telemetry/opentelemetry-python/pull/1451))
- `opentelemetry-exporter-otlp` Headers are now passed in as tuple as metadata, instead of a
  string, which was incorrect.
  ([#1507](https://github.com/open-telemetry/opentelemetry-python/pull/1507))
- `opentelemetry-exporter-jaeger` Updated Jaeger exporter status code tag
  ([#1488](https://github.com/open-telemetry/opentelemetry-python/pull/1488))
- `opentelemetry-api` `opentelemety-sdk` Moved `idsgenerator` into sdk
  ([#1514](https://github.com/open-telemetry/opentelemetry-python/pull/1514))
- `opentelemetry-sdk` The B3Format propagator has been moved into its own package: `opentelemetry-propagator-b3`
  ([#1513](https://github.com/open-telemetry/opentelemetry-python/pull/1513))
- Update default port for OTLP exporter from 55680 to 4317
  ([#1516](https://github.com/open-telemetry/opentelemetry-python/pull/1516))
- `opentelemetry-exporter-zipkin` Update boolean attribute value transformation
  ([#1509](https://github.com/open-telemetry/opentelemetry-python/pull/1509))
- Move opentelemetry-opentracing-shim out of instrumentation folder
  ([#1533](https://github.com/open-telemetry/opentelemetry-python/pull/1533))
- `opentelemetry-sdk` The JaegerPropagator has been moved into its own package: `opentelemetry-propagator-jaeger`
  ([#1525](https://github.com/open-telemetry/opentelemetry-python/pull/1525))
- `opentelemetry-exporter-jaeger`, `opentelemetry-exporter-zipkin` Update InstrumentationInfo tag keys for Jaeger and
  Zipkin exporters
  ([#1535](https://github.com/open-telemetry/opentelemetry-python/pull/1535))
- `opentelemetry-sdk` Remove rate property setter from TraceIdRatioBasedSampler
  ([#1536](https://github.com/open-telemetry/opentelemetry-python/pull/1536))
- Fix TraceState to adhere to specs
  ([#1502](https://github.com/open-telemetry/opentelemetry-python/pull/1502))
- Update Resource `merge` key conflict precedence
  ([#1544](https://github.com/open-telemetry/opentelemetry-python/pull/1544))

### Removed

- `opentelemetry-api` Remove ThreadLocalRuntimeContext since python3.4 is not supported.

## Version 0.16b1 (2020-11-26)

### Added

- Add meter reference to observers
  ([#1425](https://github.com/open-telemetry/opentelemetry-python/pull/1425))

>>>>>>> upstream/main
## Version 0.16b0 (2020-11-25)

### Added

<<<<<<< HEAD
- `opentelemetry-instrumentation-flask` Add span name callback
  ([#152](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/152))
- `opentelemetry-sdk-extension-aws` Add AWS X-Ray Ids Generator Entry Point
  ([#201](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/201))
- `opentelemetry-sdk-extension-aws` Fix typo for installing OTel SDK in docs
  ([#200](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/200))
- `opentelemetry-sdk-extension-aws` Import missing components for docs
  ([#198](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/198))
- `opentelemetry-sdk-extension-aws` Provide components needed to Configure OTel SDK for Tracing with AWS X-Ray
  ([#130](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/130))
- `opentelemetry-instrumentation-sklearn` Initial release
  ([#151](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/151))
- `opentelemetry-instrumentation-requests` Add span name callback
  ([#158](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/158))
- `opentelemetry-instrumentation-botocore` Add propagator injection for botocore calls
  ([#181](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/181))

### Changed

- `opentelemetry-instrumentation-pymemcache` Update pymemcache instrumentation to follow semantic conventions
  ([#183](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/183))
- `opentelemetry-instrumentation-redis` Update redis instrumentation to follow semantic conventions
  ([#184](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/184))
- `opentelemetry-instrumentation-pymongo` Update pymongo instrumentation to follow semantic conventions
  ([#203](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/203))
- `opentelemetry-instrumentation-sqlalchemy` Update sqlalchemy instrumentation to follow semantic conventions
  ([#202](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/202))
- `opentelemetry-instrumentation-botocore` Make botocore instrumentation check if instrumentation has been suppressed
  ([#182](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/182))
- `opentelemetry-instrumentation-botocore` Botocore SpanKind as CLIENT and modify existing traced attributes
  ([#150](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/150))
- `opentelemetry-instrumentation-dbapi` Update dbapi and its dependent instrumentations to follow semantic conventions
  ([#195](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/195))
- `opentelemetry-instrumentation-dbapi` Stop capturing query parameters by default
  ([#156](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/156))
- `opentelemetry-instrumentation-asyncpg` Update asyncpg instrumentation to follow semantic conventions
  ([#188](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/188))
- `opentelemetry-instrumentation-grpc` Update protobuf versions
  ([#1356](https://github.com/open-telemetry/opentelemetry-python/pull/1356))
=======
- Add optional parameter to `record_exception` method
  ([#1314](https://github.com/open-telemetry/opentelemetry-python/pull/1314))
- Add pickle support to SpanContext class
  ([#1380](https://github.com/open-telemetry/opentelemetry-python/pull/1380))
- Add instrumentation library name and version to OTLP exported metrics
  ([#1418](https://github.com/open-telemetry/opentelemetry-python/pull/1418))
- Add Gzip compression for exporter
  ([#1141](https://github.com/open-telemetry/opentelemetry-python/pull/1141))
- Support for v2 api protobuf format
  ([#1318](https://github.com/open-telemetry/opentelemetry-python/pull/1318))
- Add IDs Generator as Configurable Property of Auto Instrumentation
  ([#1404](https://github.com/open-telemetry/opentelemetry-python/pull/1404))
- Added support for `OTEL_EXPORTER` to the `opentelemetry-instrument` command
  ([#1036](https://github.com/open-telemetry/opentelemetry-python/pull/1036))

### Changed

- Change temporality for Counter and UpDownCounter
  ([#1384](https://github.com/open-telemetry/opentelemetry-python/pull/1384))
- OTLP exporter: Handle error case when no credentials supplied
  ([#1366](https://github.com/open-telemetry/opentelemetry-python/pull/1366))
- Update protobuf versions
  ([#1356](https://github.com/open-telemetry/opentelemetry-python/pull/1356))
- Add missing references to instrumented packages
  ([#1416](https://github.com/open-telemetry/opentelemetry-python/pull/1416))
- Instrumentation Package depends on the OTel SDK
  ([#1405](https://github.com/open-telemetry/opentelemetry-python/pull/1405))
- Allow samplers to modify tracestate
  ([#1319](https://github.com/open-telemetry/opentelemetry-python/pull/1319))
- Update exception handling optional parameters, add escaped attribute to record_exception
  ([#1365](https://github.com/open-telemetry/opentelemetry-python/pull/1365))
- Rename `MetricRecord` to `ExportRecord`
  ([#1367](https://github.com/open-telemetry/opentelemetry-python/pull/1367))
- Rename `Record` to `Accumulation`
  ([#1373](https://github.com/open-telemetry/opentelemetry-python/pull/1373))
- Rename `Meter` to `Accumulator`
  ([#1372](https://github.com/open-telemetry/opentelemetry-python/pull/1372))
- Fix `ParentBased` sampler for implicit parent spans. Fix also `trace_state`
  erasure for dropped spans or spans sampled by the `TraceIdRatioBased` sampler.
  ([#1394](https://github.com/open-telemetry/opentelemetry-python/pull/1394))
>>>>>>> upstream/main

## Version 0.15b0 (2020-11-02)

### Added

<<<<<<< HEAD
- `opentelemetry-instrumentation-requests` Add support for tracking http metrics
  ([#1230](https://github.com/open-telemetry/opentelemetry-python/pull/1230))
- `opentelemetry-instrumentation-django` Added capture of http.route
  ([#1226](https://github.com/open-telemetry/opentelemetry-python/issues/1226))
- `opentelemetry-instrumentation-django` Add support for tracking http metrics
  ([#1230](https://github.com/open-telemetry/opentelemetry-python/pull/1230))

### Changed

- `opentelemetry-exporter-datadog` Make `SpanProcessor.on_start` accept parent Context
  ([#1251](https://github.com/open-telemetry/opentelemetry-python/pull/1251))
- `opentelemetry-instrumentation-flask` Use `url.rule` instead of `request.endpoint` for span name
  ([#1260](https://github.com/open-telemetry/opentelemetry-python/pull/1260))
- `opentelemetry-instrumentation-django` Django instrumentation is now enabled by default but can be disabled by setting `OTEL_PYTHON_DJANGO_INSTRUMENT` to `False`
  ([#1239](https://github.com/open-telemetry/opentelemetry-python/pull/1239))
- `opentelemetry-instrumentation-django` Bugfix use request.path replace request.get_full_path(). It will get correct span name
  ([#1309](https://github.com/open-telemetry/opentelemetry-python/pull/1309#))
- `opentelemetry-instrumentation-django` Record span status and http.status_code attribute on exception
  ([#1257](https://github.com/open-telemetry/opentelemetry-python/pull/1257))
- `opentelemetry-instrumentation-grpc` Rewrite gRPC server interceptor
  ([#1171](https://github.com/open-telemetry/opentelemetry-python/pull/1171))
=======
- Add Env variables in OTLP exporter
  ([#1101](https://github.com/open-telemetry/opentelemetry-python/pull/1101))
- Add support for Jaeger Span Exporter configuration by environment variables and<br/>
  change JaegerSpanExporter constructor parameters
  ([#1114](https://github.com/open-telemetry/opentelemetry-python/pull/1114))

### Changed

- Updating status codes to adhere to specs
  ([#1282](https://github.com/open-telemetry/opentelemetry-python/pull/1282))
- Set initial checkpoint timestamp in aggregators
  ([#1237](https://github.com/open-telemetry/opentelemetry-python/pull/1237))
- Make `SpanProcessor.on_start` accept parent Context
  ([#1251](https://github.com/open-telemetry/opentelemetry-python/pull/1251))
- Fix b3 propagator entrypoint
  ([#1265](https://github.com/open-telemetry/opentelemetry-python/pull/1265))
- Allow None in sequence attributes values
  ([#998](https://github.com/open-telemetry/opentelemetry-python/pull/998))
- Samplers to accept parent Context
  ([#1267](https://github.com/open-telemetry/opentelemetry-python/pull/1267))
- Span.is_recording() returns false after span has ended
  ([#1289](https://github.com/open-telemetry/opentelemetry-python/pull/1289))
- Allow samplers to modify tracestate
  ([#1319](https://github.com/open-telemetry/opentelemetry-python/pull/1319))
- Remove TracerProvider coupling from Tracer init
  ([#1295](https://github.com/open-telemetry/opentelemetry-python/pull/1295))
>>>>>>> upstream/main

## Version 0.14b0 (2020-10-13)

### Added

<<<<<<< HEAD
- `opentelemetry-exporter-datadog` Add support for span resource labels and service name
- `opentelemetry-instrumentation-celery` Span operation names now include the task type.
  ([#1135](https://github.com/open-telemetry/opentelemetry-python/pull/1135))
- `opentelemetry-instrumentation-celery` Added automatic context propagation.
  ([#1135](https://github.com/open-telemetry/opentelemetry-python/pull/1135))
- `opentelemetry-instrumentation-falcon` Added support for `OTEL_PYTHON_FALCON_TRACED_REQUEST_ATTRS`
  ([#1158](https://github.com/open-telemetry/opentelemetry-python/pull/1158))
- `opentelemetry-instrumentation-tornado` Added support for `OTEL_PYTHON_TORNADO_TRACED_REQUEST_ATTRS`
  ([#1178](https://github.com/open-telemetry/opentelemetry-python/pull/1178))
- `opentelemetry-instrumentation-django` Added support for `OTEL_PYTHON_DJANGO_TRACED_REQUEST_ATTRS`
  ([#1154](https://github.com/open-telemetry/opentelemetry-python/pull/1154))

### Changed

- `opentelemetry-instrumentation-pymongo` Cast PyMongo commands as strings
  ([#1132](https://github.com/open-telemetry/opentelemetry-python/pull/1132))
- `opentelemetry-instrumentation-system-metrics` Fix issue when specific metrics are not available in certain OS
  ([#1207](https://github.com/open-telemetry/opentelemetry-python/pull/1207))
- `opentelemetry-instrumentation-pymysql` Bumped version from 0.9.3 to 0.10.1
  ([#1228](https://github.com/open-telemetry/opentelemetry-python/pull/1228))
- `opentelemetry-instrumentation-django` Changed span name extraction from request to comply semantic convention
  ([#992](https://github.com/open-telemetry/opentelemetry-python/pull/992))
=======
- Add optional parameter to `record_exception` method
  ([#1242](https://github.com/open-telemetry/opentelemetry-python/pull/1242))
- Add support for `OTEL_PROPAGATORS`
  ([#1123](https://github.com/open-telemetry/opentelemetry-python/pull/1123))
- Add keys method to TextMap propagator Getter
  ([#1196](https://github.com/open-telemetry/opentelemetry-python/issues/1196))
- Add timestamps to OTLP exporter
  ([#1199](https://github.com/open-telemetry/opentelemetry-python/pull/1199))
- Add Global Error Handler
  ([#1080](https://github.com/open-telemetry/opentelemetry-python/pull/1080))
- Add support for `OTEL_BSP_MAX_QUEUE_SIZE`, `OTEL_BSP_SCHEDULE_DELAY_MILLIS`, `OTEL_BSP_MAX_EXPORT_BATCH_SIZE`
  and `OTEL_BSP_EXPORT_TIMEOUT_MILLIS` environment variables
  ([#1105](https://github.com/open-telemetry/opentelemetry-python/pull/1120))
- Adding Resource to MeterRecord
  ([#1209](https://github.com/open-telemetry/opentelemetry-python/pull/1209))
  s

### Changed

- Store `int`s as `int`s in the global Configuration object
  ([#1118](https://github.com/open-telemetry/opentelemetry-python/pull/1118))
- Allow for Custom Trace and Span IDs Generation - `IdsGenerator` for TracerProvider
  ([#1153](https://github.com/open-telemetry/opentelemetry-python/pull/1153))
- Update baggage propagation header
  ([#1194](https://github.com/open-telemetry/opentelemetry-python/pull/1194))
- Make instances of SpanContext immutable
  ([#1134](https://github.com/open-telemetry/opentelemetry-python/pull/1134))
- Parent is now always passed in via Context, instead of Span or SpanContext
  ([#1146](https://github.com/open-telemetry/opentelemetry-python/pull/1146))
- Update OpenTelemetry protos to v0.5.0
  ([#1143](https://github.com/open-telemetry/opentelemetry-python/pull/1143))
- Zipkin exporter now accepts a `max_tag_value_length` attribute to customize the
  maximum allowed size a tag value can have.
  ([#1151](https://github.com/open-telemetry/opentelemetry-python/pull/1151))
- Fixed OTLP events to Zipkin annotations translation.
  ([#1161](https://github.com/open-telemetry/opentelemetry-python/pull/1161))
- Fixed bootstrap command to correctly install opentelemetry-instrumentation-falcon instead of
  opentelemetry-instrumentation-flask.
  ([#1138](https://github.com/open-telemetry/opentelemetry-python/pull/1138))
- Update sampling result names
  ([#1128](https://github.com/open-telemetry/opentelemetry-python/pull/1128))
- Event attributes are now immutable
  ([#1195](https://github.com/open-telemetry/opentelemetry-python/pull/1195))
- Renaming metrics Batcher to Processor
  ([#1203](https://github.com/open-telemetry/opentelemetry-python/pull/1203))
- Protect access to Span implementation
  ([#1188](https://github.com/open-telemetry/opentelemetry-python/pull/1188))
- `start_as_current_span` and `use_span` can now optionally auto-record any exceptions raised inside the context
  manager.
  ([#1162](https://github.com/open-telemetry/opentelemetry-python/pull/1162))
>>>>>>> upstream/main

## Version 0.13b0 (2020-09-17)

### Added

<<<<<<< HEAD
- `opentelemetry-instrumentation-falcon` Initial release. Added instrumentation for Falcon 2.0+
- `opentelemetry-instrumentation-tornado` Initial release. Supports Tornado 6.x on Python 3.5 and newer.
- `opentelemetry-instrumentation-aiohttp-client` Add instrumentor and auto instrumentation support for aiohttp
  ([#1075](https://github.com/open-telemetry/opentelemetry-python/pull/1075))
- `opentelemetry-instrumentation-requests` Add support for instrumenting prepared requests
  ([#1040](https://github.com/open-telemetry/opentelemetry-python/pull/1040))
- `opentelemetry-instrumentation-requests` Add support for http metrics
  ([#1116](https://github.com/open-telemetry/opentelemetry-python/pull/1116))

### Changed

- `opentelemetry-instrumentation-aiohttp-client` Updating span name to match semantic conventions
  ([#972](https://github.com/open-telemetry/opentelemetry-python/pull/972))
- `opentelemetry-instrumentation-dbapi` cursors and connections now produce spans when used with context managers
  ([#1028](https://github.com/open-telemetry/opentelemetry-python/pull/1028))
=======
- Add instrumentation info to exported spans
  ([#1095](https://github.com/open-telemetry/opentelemetry-python/pull/1095))
- Add metric OTLP exporter
  ([#835](https://github.com/open-telemetry/opentelemetry-python/pull/835))
- Add type hints to OTLP exporter
  ([#1121](https://github.com/open-telemetry/opentelemetry-python/pull/1121))
- Add support for OTEL_EXPORTER_ZIPKIN_ENDPOINT env var. As part of this change, the
  configuration of the ZipkinSpanExporter exposes a `url` argument to replace `host_name`,
  `port`, `protocol`, `endpoint`. This brings this implementation inline with other
  implementations.
  ([#1064](https://github.com/open-telemetry/opentelemetry-python/pull/1064))
- Zipkin exporter report instrumentation info.
  ([#1097](https://github.com/open-telemetry/opentelemetry-python/pull/1097))
- Add status mapping to tags
  ([#1111](https://github.com/open-telemetry/opentelemetry-python/issues/1111))
- Report instrumentation info
  ([#1098](https://github.com/open-telemetry/opentelemetry-python/pull/1098))
- Add support for http metrics
  ([#1116](https://github.com/open-telemetry/opentelemetry-python/pull/1116))
- Populate resource attributes as per semantic conventions
  ([#1053](https://github.com/open-telemetry/opentelemetry-python/pull/1053))

### Changed

- Refactor `SpanContext.is_valid` from a method to a data attribute
  ([#1005](https://github.com/open-telemetry/opentelemetry-python/pull/1005))
- Moved samplers from API to SDK
  ([#1023](https://github.com/open-telemetry/opentelemetry-python/pull/1023))
- Change return value type of `correlationcontext.get_correlations` to immutable `MappingProxyType`
  ([#1024](https://github.com/open-telemetry/opentelemetry-python/pull/1024))
- Sampling spec changes
  ([#1034](https://github.com/open-telemetry/opentelemetry-python/pull/1034))
- Remove lazy Event and Link API from Span interface
  ([#1045](https://github.com/open-telemetry/opentelemetry-python/pull/1045))
- Rename CorrelationContext to Baggage
  ([#1060](https://github.com/open-telemetry/opentelemetry-python/pull/1060))
- Rename HTTPTextFormat to TextMapPropagator. This change also updates `get_global_httptextformat` and
  `set_global_httptextformat` to `get_global_textmap` and `set_global_textmap`
  ([#1085](https://github.com/open-telemetry/opentelemetry-python/pull/1085))
- Fix api/sdk setup.cfg to include missing python files
  ([#1091](https://github.com/open-telemetry/opentelemetry-python/pull/1091))
- Improve BatchExportSpanProcessor
  ([#1062](https://github.com/open-telemetry/opentelemetry-python/pull/1062))
- Rename Resource labels to attributes
  ([#1082](https://github.com/open-telemetry/opentelemetry-python/pull/1082))
- Rename members of `trace.sampling.Decision` enum
  ([#1115](https://github.com/open-telemetry/opentelemetry-python/pull/1115))
- Merge `OTELResourceDetector` result when creating resources
  ([#1096](https://github.com/open-telemetry/opentelemetry-python/pull/1096))
>>>>>>> upstream/main

### Removed

- Drop support for Python 3.4
  ([#1099](https://github.com/open-telemetry/opentelemetry-python/pull/1099))

## Version 0.12b0 (2020-08-14)

<<<<<<< HEAD
### Changed

- `opentelemetry-ext-pymemcache` Change package name to opentelemetry-instrumentation-pymemcache
  ([#966](https://github.com/open-telemetry/opentelemetry-python/pull/966))
- `opentelemetry-ext-redis` Update default SpanKind to `SpanKind.CLIENT`
  ([#965](https://github.com/open-telemetry/opentelemetry-python/pull/965))
- `opentelemetry-ext-redis` Change package name to opentelemetry-instrumentation-redis
  ([#966](https://github.com/open-telemetry/opentelemetry-python/pull/966))
- `opentelemetry-ext-datadog` Change package name to opentelemetry-exporter-datadog
  ([#953](https://github.com/open-telemetry/opentelemetry-python/pull/953))
- `opentelemetry-ext-jinja2` Change package name to opentelemetry-instrumentation-jinja2
  ([#969](https://github.com/open-telemetry/opentelemetry-python/pull/969))
- `opentelemetry-ext-elasticsearch` Update environment variable names, prefix changed from `OPENTELEMETRY` to `OTEL`
  ([#904](https://github.com/open-telemetry/opentelemetry-python/pull/904))
- `opentelemetry-ext-elasticsearch` Change package name to opentelemetry-instrumentation-elasticsearch
  ([#969](https://github.com/open-telemetry/opentelemetry-python/pull/969))
- `opentelemetry-ext-celery` Change package name to opentelemetry-instrumentation-celery
  ([#969](https://github.com/open-telemetry/opentelemetry-python/pull/969))
- `opentelemetry-ext-pyramid` Change package name to opentelemetry-instrumentation-pyramid
  ([#966](https://github.com/open-telemetry/opentelemetry-python/pull/966))
- `opentelemetry-ext-pyramid` Update environment variable names, prefix changed from `OPENTELEMETRY` to `OTEL`
  ([#904](https://github.com/open-telemetry/opentelemetry-python/pull/904))
- `opentelemetry-ext-pymongo` Change package name to opentelemetry-instrumentation-pymongo
  ([#966](https://github.com/open-telemetry/opentelemetry-python/pull/966))
- `opentelemetry-ext-sqlite3` Change package name to opentelemetry-instrumentation-sqlite3
  ([#966](https://github.com/open-telemetry/opentelemetry-python/pull/966))
- `opentelemetry-ext-sqlalchemy` Change package name to opentelemetry-instrumentation-sqlalchemy
  ([#966](https://github.com/open-telemetry/opentelemetry-python/pull/966))
- `opentelemetry-ext-psycopg2` Change package name to opentelemetry-instrumentation-psycopg2
  ([#966](https://github.com/open-telemetry/opentelemetry-python/pull/966))
- `opentelemetry-ext-aiohttp-client` Change package name to opentelemetry-instrumentation-aiohttp-client
  ([#961](https://github.com/open-telemetry/opentelemetry-python/pull/961))
- `opentelemetry-ext-boto` Change package name to opentelemetry-instrumentation-boto
  ([#969](https://github.com/open-telemetry/opentelemetry-python/pull/969))
- `opentelemetry-ext-system-metrics` Change package name to opentelemetry-instrumentation-system-metrics
  ([#969](https://github.com/open-telemetry/opentelemetry-python/pull/969))
- `opentelemetry-ext-asgi` Change package name to opentelemetry-instrumentation-asgi
  ([#961](https://github.com/open-telemetry/opentelemetry-python/pull/961))
- `opentelemetry-ext-wsgi` Change package name to opentelemetry-instrumentation-wsgi
  ([#961](https://github.com/open-telemetry/opentelemetry-python/pull/961))
- `opentelemetry-ext-pymysql` Change package name to opentelemetry-instrumentation-pymysql
  ([#966](https://github.com/open-telemetry/opentelemetry-python/pull/966))
- `opentelemetry-ext-requests` Change package name to opentelemetry-instrumentation-requests
  ([#961](https://github.com/open-telemetry/opentelemetry-python/pull/961))
- `opentelemetry-ext-requests` Span name reported updated to follow semantic conventions to reduce
  cardinality ([#972](https://github.com/open-telemetry/opentelemetry-python/pull/972))
- `opentelemetry-ext-botocore` Change package name to opentelemetry-instrumentation-botocore
  ([#969](https://github.com/open-telemetry/opentelemetry-python/pull/969))
- `opentelemetry-ext-dbapi` Change package name to opentelemetry-instrumentation-dbapi
  ([#966](https://github.com/open-telemetry/opentelemetry-python/pull/966))
- `opentelemetry-ext-flask` Change package name to opentelemetry-instrumentation-flask
  ([#961](https://github.com/open-telemetry/opentelemetry-python/pull/961))
- `opentelemetry-ext-flask` Update environment variable names, prefix changed from `OPENTELEMETRY` to `OTEL`
  ([#904](https://github.com/open-telemetry/opentelemetry-python/pull/904))
- `opentelemetry-ext-django` Change package name to opentelemetry-instrumentation-django
  ([#961](https://github.com/open-telemetry/opentelemetry-python/pull/961))
- `opentelemetry-ext-django` Update environment variable names, prefix changed from `OPENTELEMETRY` to `OTEL`
  ([#904](https://github.com/open-telemetry/opentelemetry-python/pull/904))
- `opentelemetry-ext-asyncpg` Change package name to opentelemetry-instrumentation-asyncpg
  ([#966](https://github.com/open-telemetry/opentelemetry-python/pull/966))
- `opentelemetry-ext-mysql` Change package name to opentelemetry-instrumentation-mysql
  ([#966](https://github.com/open-telemetry/opentelemetry-python/pull/966))
- `opentelemetry-ext-grpc` Change package name to opentelemetry-instrumentation-grpc
  ([#969](https://github.com/open-telemetry/opentelemetry-python/pull/969))
=======
### Added

- Implement Views in metrics SDK
  ([#596](https://github.com/open-telemetry/opentelemetry-python/pull/596))

### Changed

- Update environment variable names, prefix changed from `OPENTELEMETRY` to `OTEL`
  ([#904](https://github.com/open-telemetry/opentelemetry-python/pull/904))
- Stop TracerProvider and MeterProvider from being overridden
  ([#959](https://github.com/open-telemetry/opentelemetry-python/pull/959))
- Update default port to 55680
  ([#977](https://github.com/open-telemetry/opentelemetry-python/pull/977))
- Add proper length zero padding to hex strings of traceId, spanId, parentId sent on the wire, for compatibility with
  jaeger-collector
  ([#908](https://github.com/open-telemetry/opentelemetry-python/pull/908))
- Send start_timestamp and convert labels to strings
  ([#937](https://github.com/open-telemetry/opentelemetry-python/pull/937))
- Renamed several packages
  ([#953](https://github.com/open-telemetry/opentelemetry-python/pull/953))
- Thrift URL for Jaeger exporter doesn't allow HTTPS (hardcoded to HTTP)
  ([#978](https://github.com/open-telemetry/opentelemetry-python/pull/978))
- Change reference names to opentelemetry-instrumentation-opentracing-shim
  ([#969](https://github.com/open-telemetry/opentelemetry-python/pull/969))
- Changed default Sampler to `ParentOrElse(AlwaysOn)`
  ([#960](https://github.com/open-telemetry/opentelemetry-python/pull/960))
- Update environment variable names, prefix changed from `OPENTELEMETRY` to `OTEL`
  ([#904](https://github.com/open-telemetry/opentelemetry-python/pull/904))
- Update environment variable `OTEL_RESOURCE` to `OTEL_RESOURCE_ATTRIBUTES` as per
  the specification
>>>>>>> upstream/main

## Version 0.11b0 (2020-07-28)

### Added

<<<<<<< HEAD
- `opentelemetry-instrumentation-aiopg` Initial release
- `opentelemetry-instrumentation-fastapi` Initial release
  ([#890](https://github.com/open-telemetry/opentelemetry-python/pull/890))
- `opentelemetry-ext-grpc` Add status code to gRPC client spans
  ([896](https://github.com/open-telemetry/opentelemetry-python/pull/896))
- `opentelemetry-ext-grpc` Add gRPC client and server instrumentors
  ([788](https://github.com/open-telemetry/opentelemetry-python/pull/788))
- `opentelemetry-ext-grpc` Add metric recording (bytes in/out, errors, latency) to gRPC client

### Changed

- `opentelemetry-ext-pyramid` Use one general exclude list instead of two
  ([#872](https://github.com/open-telemetry/opentelemetry-python/pull/872))
- `opentelemetry-ext-boto` fails to export spans via jaeger
  ([#866](https://github.com/open-telemetry/opentelemetry-python/pull/866))
- `opentelemetry-ext-botocore` fails to export spans via jaeger
  ([#866](https://github.com/open-telemetry/opentelemetry-python/pull/866))
- `opentelemetry-ext-wsgi` Set span status on wsgi errors
  ([#864](https://github.com/open-telemetry/opentelemetry-python/pull/864))
- `opentelemetry-ext-flask` Use one general exclude list instead of two
  ([#872](https://github.com/open-telemetry/opentelemetry-python/pull/872))
- `opentelemetry-ext-django` Use one general exclude list instead of two
  ([#872](https://github.com/open-telemetry/opentelemetry-python/pull/872))
- `opentelemetry-ext-asyncpg` Shouldn't capture query parameters by default
  ([#854](https://github.com/open-telemetry/opentelemetry-python/pull/854))
- `opentelemetry-ext-mysql` bugfix: Fix auto-instrumentation entry point for mysql
  ([#858](https://github.com/open-telemetry/opentelemetry-python/pull/858))

## Version 0.10b0 (2020-06-23)

### Added

- `opentelemetry-ext-pymemcache` Initial release
- `opentelemetry-ext-elasticsearch` Initial release
- `opentelemetry-ext-celery` Add instrumentation for Celery
  ([#780](https://github.com/open-telemetry/opentelemetry-python/pull/780))
- `opentelemetry-instrumentation-starlette` Initial release
  ([#777](https://github.com/open-telemetry/opentelemetry-python/pull/777))
- `opentelemetry-ext-asyncpg` Initial Release
  ([#814](https://github.com/open-telemetry/opentelemetry-python/pull/814))
=======
- Add support for resources and resource detector
  ([#853](https://github.com/open-telemetry/opentelemetry-python/pull/853))

### Changed

- Return INVALID_SPAN if no TracerProvider set for get_current_span
  ([#751](https://github.com/open-telemetry/opentelemetry-python/pull/751))
- Rename record_error to record_exception
  ([#927](https://github.com/open-telemetry/opentelemetry-python/pull/927))
- Update span exporter to use OpenTelemetry Proto v0.4.0
  ([#872](https://github.com/open-telemetry/opentelemetry-python/pull/889))

## Version 0.10b0 (2020-06-23)

### Changed

- Regenerate proto code and add pyi stubs
  ([#823](https://github.com/open-telemetry/opentelemetry-python/pull/823))
- Rename CounterAggregator -> SumAggregator
  ([#816](https://github.com/open-telemetry/opentelemetry-python/pull/816))
>>>>>>> upstream/main

## Version 0.9b0 (2020-06-10)

### Added

<<<<<<< HEAD
- `opentelemetry-ext-pyramid` Initial release
- `opentelemetry-ext-boto` Initial release
- `opentelemetry-ext-botocore` Initial release
- `opentelemetry-ext-system-metrics` Initial release
  (https://github.com/open-telemetry/opentelemetry-python/pull/652)
=======
- Adding trace.get_current_span, Removing Tracer.get_current_span
  ([#552](https://github.com/open-telemetry/opentelemetry-python/pull/552))
- Add SumObserver, UpDownSumObserver and LastValueAggregator in metrics
  ([#789](https://github.com/open-telemetry/opentelemetry-python/pull/789))
- Add start_pipeline to MeterProvider
  ([#791](https://github.com/open-telemetry/opentelemetry-python/pull/791))
- Initial release of opentelemetry-ext-otlp, opentelemetry-proto

### Changed

- Move stateful & resource from Meter to MeterProvider
  ([#751](https://github.com/open-telemetry/opentelemetry-python/pull/751))
- Rename Measure to ValueRecorder in metrics
  ([#761](https://github.com/open-telemetry/opentelemetry-python/pull/761))
- Rename Observer to ValueObserver
  ([#764](https://github.com/open-telemetry/opentelemetry-python/pull/764))
- Log a warning when replacing the global Tracer/Meter provider
  ([#856](https://github.com/open-telemetry/opentelemetry-python/pull/856))
- bugfix: byte type attributes are decoded before adding to attributes dict
  ([#775](https://github.com/open-telemetry/opentelemetry-python/pull/775))
- Rename opentelemetry-auto-instrumentation to opentelemetry-instrumentation,
  and console script `opentelemetry-auto-instrumentation` to `opentelemetry-instrument`
>>>>>>> upstream/main

## Version 0.8b0 (2020-05-27)

### Added

<<<<<<< HEAD
- `opentelemetry-ext-datadog` Add exporter to Datadog
  ([#572](https://github.com/open-telemetry/opentelemetry-python/pull/572))
- `opentelemetry-ext-sqlite3` Initial release
- `opentelemetry-ext-psycopg2` Implement instrumentor interface, enabling auto-instrumentation
  ([#694](https://github.com/open-telemetry/opentelemetry-python/pull/694))
- `opentelemetry-ext-asgi` Add ASGI middleware
  ([#716](https://github.com/open-telemetry/opentelemetry-python/pull/716))
- `opentelemetry-ext-django` Add exclude list for paths and hosts to prevent from tracing
  ([#670](https://github.com/open-telemetry/opentelemetry-python/pull/670))
- `opentelemetry-ext-django` Add support for django >= 1.10 (#717)

### Changed

- `opentelemetry-ext-grpc` lint: version of grpc causes lint issues
  ([#696](https://github.com/open-telemetry/opentelemetry-python/pull/696))
=======
- Add a new bootstrap command that enables automatic instrument installations.
  ([#650](https://github.com/open-telemetry/opentelemetry-python/pull/650))

### Changed

- Handle boolean, integer and float values in Configuration
  ([#662](https://github.com/open-telemetry/opentelemetry-python/pull/662))
- bugfix: ensure status is always string
  ([#640](https://github.com/open-telemetry/opentelemetry-python/pull/640))
- Transform resource to tags when exporting
  ([#707](https://github.com/open-telemetry/opentelemetry-python/pull/707))
- Rename otcollector to opencensus
  ([#695](https://github.com/open-telemetry/opentelemetry-python/pull/695))
- Transform resource to tags when exporting
  ([#645](https://github.com/open-telemetry/opentelemetry-python/pull/645))
- `ext/boto`: Could not serialize attribute aws.region to tag when exporting via jaeger
  Serialize tuple type values by coercing them into a string, since Jaeger does not
  support tuple types.
  ([#865](https://github.com/open-telemetry/opentelemetry-python/pull/865))
- Validate span attribute types in SDK
  ([#678](https://github.com/open-telemetry/opentelemetry-python/pull/678))
- Specify to_json indent from arguments
  ([#718](https://github.com/open-telemetry/opentelemetry-python/pull/718))
- Span.resource will now default to an empty resource
  ([#724](https://github.com/open-telemetry/opentelemetry-python/pull/724))
- bugfix: Fix error message
  ([#729](https://github.com/open-telemetry/opentelemetry-python/pull/729))
- deep copy empty attributes
  ([#714](https://github.com/open-telemetry/opentelemetry-python/pull/714))
>>>>>>> upstream/main

## Version 0.7b1 (2020-05-12)

### Added

<<<<<<< HEAD
- `opentelemetry-ext-redis` Initial release
- `opentelemetry-ext-jinja2` Add jinja2 instrumentation
  ([#643](https://github.com/open-telemetry/opentelemetry-python/pull/643))
- `opentelemetry-ext-pymongo` Implement instrumentor interface
  ([#612](https://github.com/open-telemetry/opentelemetry-python/pull/612))
- `opentelemetry-ext-sqlalchemy` Initial release
- `opentelemetry-ext-aiohttp-client` Initial release
- `opentelemetry-ext-pymysql` Initial release
- `opentelemetry-ext-http-requests` Implement instrumentor interface, enabling auto-instrumentation
  ([#597](https://github.com/open-telemetry/opentelemetry-python/pull/597))
- `opentelemetry-ext-http-requests` Adding disable_session for more granular instrumentation control
  ([#573](https://github.com/open-telemetry/opentelemetry-python/pull/573))
- `opentelemetry-ext-http-requests` Add a callback for custom attributes
  ([#656](https://github.com/open-telemetry/opentelemetry-python/pull/656))
- `opentelemetry-ext-dbapi` Implement instrument_connection and uninstrument_connection
  ([#624](https://github.com/open-telemetry/opentelemetry-python/pull/624))
- `opentelemetry-ext-flask` Add exclude list for paths and hosts
  ([#630](https://github.com/open-telemetry/opentelemetry-python/pull/630))
- `opentelemetry-ext-django` Initial release
- `opentelemetry-ext-mysql` Implement instrumentor interface
  ([#654](https://github.com/open-telemetry/opentelemetry-python/pull/654))

### Changed

- `opentelemetry-ext-http-requests` Rename package to opentelemetry-ext-requests
  ([#619](https://github.com/open-telemetry/opentelemetry-python/pull/619))
=======
- Add reset for the global configuration object, for testing purposes
  ([#636](https://github.com/open-telemetry/opentelemetry-python/pull/636))
- Add support for programmatic instrumentation
  ([#579](https://github.com/open-telemetry/opentelemetry-python/pull/569))

### Changed

- tracer.get_tracer now optionally accepts a TracerProvider
  ([#602](https://github.com/open-telemetry/opentelemetry-python/pull/602))
- Configuration object can now be used by any component of opentelemetry,
  including 3rd party instrumentations
  ([#563](https://github.com/open-telemetry/opentelemetry-python/pull/563))
- bugfix: configuration object now matches fields in a case-sensitive manner
  ([#583](https://github.com/open-telemetry/opentelemetry-python/pull/583))
- bugfix: configuration object now accepts all valid python variable names
  ([#583](https://github.com/open-telemetry/opentelemetry-python/pull/583))
- bugfix: configuration undefined attributes now return None instead of raising
  an AttributeError.
  ([#583](https://github.com/open-telemetry/opentelemetry-python/pull/583))
- bugfix: 'debug' field is now correct
  ([#549](https://github.com/open-telemetry/opentelemetry-python/pull/549))
- bugfix: enable auto-instrumentation command to work for custom entry points
  (e.g. flask_run)
  ([#567](https://github.com/open-telemetry/opentelemetry-python/pull/567))
- Exporter API: span parents are now always spancontext
  ([#548](https://github.com/open-telemetry/opentelemetry-python/pull/548))
- Console span exporter now prints prettier, more legible messages
  ([#505](https://github.com/open-telemetry/opentelemetry-python/pull/505))
- bugfix: B3 propagation now retrieves parentSpanId correctly
  ([#621](https://github.com/open-telemetry/opentelemetry-python/pull/621))
- bugfix: a DefaultSpan now longer causes an exception when used with tracer
  ([#577](https://github.com/open-telemetry/opentelemetry-python/pull/577))
- move last_updated_timestamp into aggregators instead of bound metric
  instrument
  ([#522](https://github.com/open-telemetry/opentelemetry-python/pull/522))
- bugfix: suppressing instrumentation in metrics to eliminate an infinite loop
  of telemetry
  ([#529](https://github.com/open-telemetry/opentelemetry-python/pull/529))
- bugfix: freezing span attribute sequences, reducing potential user errors
  ([#529](https://github.com/open-telemetry/opentelemetry-python/pull/529))
>>>>>>> upstream/main

## Version 0.6b0 (2020-03-30)

### Added

<<<<<<< HEAD
- `opentelemetry-ext-flask` Add an entry_point to be usable in auto-instrumentation
  ([#327](https://github.com/open-telemetry/opentelemetry-python/pull/327))
- `opentelemetry-ext-grpc` Add gRPC integration
  ([#476](https://github.com/open-telemetry/opentelemetry-python/pull/476))

## Version 0.5b0 (2020-03-16)

=======
- Add support for lazy events and links
  ([#474](https://github.com/open-telemetry/opentelemetry-python/pull/474))
- Adding is_remote flag to SpanContext, indicating when a span is remote
  ([#516](https://github.com/open-telemetry/opentelemetry-python/pull/516))
- Adding a solution to release metric handles and observers
  ([#435](https://github.com/open-telemetry/opentelemetry-python/pull/435))
- Initial release: opentelemetry-instrumentation

### Changed

- Metrics API no longer uses LabelSet
  ([#527](https://github.com/open-telemetry/opentelemetry-python/pull/527))
- Allow digit as first char in vendor specific trace state key
  ([#511](https://github.com/open-telemetry/opentelemetry-python/pull/511))
- Exporting to collector now works
  ([#508](https://github.com/open-telemetry/opentelemetry-python/pull/508))

## Version 0.5b0 (2020-03-16)

### Added

- Adding Correlation Context API/SDK and propagator
  ([#471](https://github.com/open-telemetry/opentelemetry-python/pull/471))
- Adding a global configuration module to simplify setting and getting globals
  ([#466](https://github.com/open-telemetry/opentelemetry-python/pull/466))
- Adding named meters, removing batchers
  ([#431](https://github.com/open-telemetry/opentelemetry-python/pull/431))
- Adding attach/detach methods as per spec
  ([#429](https://github.com/open-telemetry/opentelemetry-python/pull/429))
- Adding OT Collector metrics exporter
  ([#454](https://github.com/open-telemetry/opentelemetry-python/pull/454))
- Initial release opentelemetry-ext-otcollector

### Changed

- Rename metric handle to bound metric instrument
  ([#470](https://github.com/open-telemetry/opentelemetry-python/pull/470))
- Moving resources to sdk
  ([#464](https://github.com/open-telemetry/opentelemetry-python/pull/464))
- Implementing propagators to API to use context
  ([#446](https://github.com/open-telemetry/opentelemetry-python/pull/446))
- Renaming TraceOptions to TraceFlags
  ([#450](https://github.com/open-telemetry/opentelemetry-python/pull/450))
- Renaming TracerSource to TracerProvider
  ([#441](https://github.com/open-telemetry/opentelemetry-python/pull/441))
- Improve validation of attributes
  ([#460](https://github.com/open-telemetry/opentelemetry-python/pull/460))
- Re-raise errors caught in opentelemetry.sdk.trace.Tracer.use_span()
  ([#469](https://github.com/open-telemetry/opentelemetry-python/pull/469))
- Implement observer instrument
  ([#425](https://github.com/open-telemetry/opentelemetry-python/pull/425))

>>>>>>> upstream/main
## Version 0.4a0 (2020-02-21)

### Added

<<<<<<< HEAD
- `opentelemetry-ext-psycopg2` Initial release
- `opentelemetry-ext-dbapi` Initial release
- `opentelemetry-ext-mysql` Initial release

### Changed

- `opentelemetry-ext-pymongo` Updating network connection attribute names
  ([#350](https://github.com/open-telemetry/opentelemetry-python/pull/350))
- `opentelemetry-ext-wsgi` Updating network connection attribute names
  ([#350](https://github.com/open-telemetry/opentelemetry-python/pull/350))
- `opentelemetry-ext-flask` Use string keys for WSGI environ values
  ([#366](https://github.com/open-telemetry/opentelemetry-python/pull/366))
=======
- Added named Tracers
  ([#301](https://github.com/open-telemetry/opentelemetry-python/pull/301))
- Add int and valid sequenced to AttributeValue type
  ([#368](https://github.com/open-telemetry/opentelemetry-python/pull/368))
- Add ABC for Metric
  ([#391](https://github.com/open-telemetry/opentelemetry-python/pull/391))
- Metrics export pipeline, and stdout exporter
  ([#341](https://github.com/open-telemetry/opentelemetry-python/pull/341))
- Adding Context API Implementation
  ([#395](https://github.com/open-telemetry/opentelemetry-python/pull/395))
- Adding trace.get_tracer function
  ([#430](https://github.com/open-telemetry/opentelemetry-python/pull/430))
- Add runtime validation for set_attribute
  ([#348](https://github.com/open-telemetry/opentelemetry-python/pull/348))
- Add support for B3 ParentSpanID
  ([#286](https://github.com/open-telemetry/opentelemetry-python/pull/286))
- Implement MinMaxSumCount aggregator
  ([#422](https://github.com/open-telemetry/opentelemetry-python/pull/422))
- Initial release opentelemetry-ext-zipkin, opentelemetry-ext-prometheus

### Changed

- Separate Default classes from interface descriptions
  ([#311](https://github.com/open-telemetry/opentelemetry-python/pull/311))
- Export span status
  ([#367](https://github.com/open-telemetry/opentelemetry-python/pull/367))
- Export span kind
  ([#387](https://github.com/open-telemetry/opentelemetry-python/pull/387))
- Set status for ended spans
  ([#297](https://github.com/open-telemetry/opentelemetry-python/pull/297) and
  [#358](https://github.com/open-telemetry/opentelemetry-python/pull/358))
- Use module loggers
  ([#351](https://github.com/open-telemetry/opentelemetry-python/pull/351))
- Protect start_time and end_time from being set manually by the user
  ([#363](https://github.com/open-telemetry/opentelemetry-python/pull/363))
- Set status in start_as_current_span
  ([#377](https://github.com/open-telemetry/opentelemetry-python/pull/377))
- Implement force_flush for span processors
  ([#389](https://github.com/open-telemetry/opentelemetry-python/pull/389))
- Set sampled flag on sampling trace
  ([#407](https://github.com/open-telemetry/opentelemetry-python/pull/407))
- Add io and formatter options to console exporter
  ([#412](https://github.com/open-telemetry/opentelemetry-python/pull/412))
- Clean up ProbabilitySample for 64 bit trace IDs
  ([#238](https://github.com/open-telemetry/opentelemetry-python/pull/238))

### Removed

- Remove monotonic and absolute metric instruments
  ([#410](https://github.com/open-telemetry/opentelemetry-python/pull/410))
>>>>>>> upstream/main

## Version 0.3a0 (2019-12-11)

### Added

<<<<<<< HEAD
- `opentelemetry-ext-flask` Initial release
- `opentelemetry-ext-pymongo` Initial release

### Changed

- `opentelemetry-ext-wsgi` Support new semantic conventions
  ([#299](https://github.com/open-telemetry/opentelemetry-python/pull/299))
- `opentelemetry-ext-wsgi` Updates for core library changes

## Version 0.2a0 (2019-10-29)

### Changed

- `opentelemetry-ext-wsgi` Updates for core library changes
- `opentelemetry-ext-http-requests` Updates for core library changes

- `Added support for PyPy3` Initial release
## [#1033](https://github.com/open-telemetryopentelemetry-python-contrib/issues/1033)
=======
- Add metrics exporters
  ([#192](https://github.com/open-telemetry/opentelemetry-python/pull/192))
- Implement extract and inject support for HTTP_HEADERS and TEXT_MAP formats
  ([#256](https://github.com/open-telemetry/opentelemetry-python/pull/256))

### Changed

- Multiple tracing API/SDK changes
- Multiple metrics API/SDK changes

### Removed

- Remove option to create unstarted spans from API
  ([#290](https://github.com/open-telemetry/opentelemetry-python/pull/290))

## Version 0.2a0 (2019-10-29)

### Added

- W3C TraceContext fixes and compliance tests
  ([#228](https://github.com/open-telemetry/opentelemetry-python/pull/228))
- Sampler API/SDK
  ([#225](https://github.com/open-telemetry/opentelemetry-python/pull/225))
- Initial release: opentelemetry-ext-jaeger, opentelemetry-opentracing-shim

### Changed

- Multiple metrics API/SDK changes
- Multiple tracing API/SDK changes
- Multiple context API changes
- Multiple bugfixes and improvements
>>>>>>> upstream/main

## Version 0.1a0 (2019-09-30)

### Added

<<<<<<< HEAD
- `opentelemetry-ext-wsgi` Initial release
- `opentelemetry-ext-http-requests` Initial release
=======
- Initial release api/sdk
>>>>>>> upstream/main
