# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> [!NOTE]
> The following components are released independently and maintain individual CHANGELOG files.
> Use [this search for a list of all CHANGELOG.md files in this repo](https://github.com/search?q=repo%3Aopen-telemetry%2Fopentelemetry-python-contrib+path%3A**%2FCHANGELOG.md&type=code).

## Unreleased

### Fixed

- `opentelemetry-instrumentation`: Fix dependency conflict detection when instrumented packages are not installed by moving check back to before instrumentors are loaded. Add "instruments-any" feature for instrumentations that target multiple packages.
  ([#3610](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3610))

### Added

- `opentelemetry-instrumentation-psycopg2` Utilize instruments-any functionality.
  ([#3610](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3610))
- `opentelemetry-instrumentation-kafka-python` Utilize instruments-any functionality.
  ([#3610](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3610))

## Version 1.35.0/0.56b0 (2025-07-11)

### Added

- `opentelemetry-instrumentation-pika` Added instrumentation for All `SelectConnection` adapters
  ([#3584](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3584))
- `opentelemetry-instrumentation-tornado` Add support for `WebSocketHandler` instrumentation
  ([#3498](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3498))
- `opentelemetry-util-http` Added support for redacting specific url query string values and url credentials in instrumentations
  ([#3508](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3508))
- `opentelemetry-instrumentation-pymongo` `aggregate` and `getMore` capture statements support
  ([#3601](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3601))

### Fixed

- `opentelemetry-instrumentation-asgi`: fix excluded_urls in instrumentation-asgi
  ([#3567](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3567))
- `opentelemetry-resource-detector-containerid`: make it more quiet on platforms without cgroups
  ([#3579](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3579))

## Version 1.34.0/0.55b0 (2025-06-04)

### Fixed

- `opentelemetry-instrumentation-system-metrics`: fix loading on Google Cloud Run
  ([#3533](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3533))
- `opentelemetry-instrumentation-fastapi`: fix wrapping of middlewares
  ([#3012](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3012))
- `opentelemetry-instrumentation-starlette` Remove max version constraint on starlette
  ([#3456](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3456))
- `opentelemetry-instrumentation-starlette` Fix memory leak and double middleware
  ([#3529](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3529))
- `opentelemetry-instrumentation-urllib3`: proper bucket boundaries in stable semconv http duration metrics
  ([#3518](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3518))
- `opentelemetry-instrumentation-urllib`: proper bucket boundaries in stable semconv http duration metrics
  ([#3519](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3519))
- `opentelemetry-instrumentation-falcon`: proper bucket boundaries in stable semconv http duration
  ([#3525](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3525))
- `opentelemetry-instrumentation-wsgi`: add explicit http duration buckets for stable semconv
  ([#3527](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3527))
- `opentelemetry-instrumentation-asgi`: add explicit http duration buckets for stable semconv
  ([#3526](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3526))
- `opentelemetry-instrumentation-flask`: proper bucket boundaries in stable semconv http duration
  ([#3523](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3523))
- `opentelemetry-instrumentation-django`: proper bucket boundaries in stable semconv http duration
  ([#3524](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3524))
- `opentelemetry-instrumentation-grpc`: support non-list interceptors
  ([#3520](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3520))
- `opentelemetry-instrumentation-botocore` Ensure spans end on early stream closure for Bedrock Streaming APIs
  ([#3481](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3481))
- `opentelemetry-instrumentation-sqlalchemy` Respect suppress_instrumentation functionality
  ([#3477](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3477))
- `opentelemetry-instrumentation-botocore`: fix handling of tool input in Bedrock ConverseStream
  ([#3544](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3544))
- `opentelemetry-instrumentation-botocore` Add type check when extracting tool use from Bedrock request message content
  ([#3548](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3548))
- `opentelemetry-instrumentation-dbapi` Respect suppress_instrumentation functionality ([#3460](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3460))
- `opentelemetry-resource-detector-container` Correctly parse container id when using systemd and cgroupsv1
  ([#3429](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3429))

### Breaking changes

- `opentelemetry-instrumentation-botocore` Use `cloud.region` instead of `aws.region` span attribute as per semantic conventions.
  ([#3474](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3474))
- `opentelemetry-instrumentation-fastapi`: Drop support for FastAPI versions earlier than `0.92`
  ([#3012](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3012))
- `opentelemetry-resource-detector-container`: rename package name to `opentelemetry-resource-detector-containerid`
  ([#3536](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3536))

### Added

- `opentelemetry-instrumentation-aiohttp-client` Add support for HTTP metrics
  ([#3517](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3517))
- `opentelemetry-instrumentation-httpx` Add support for HTTP metrics
  ([#3513](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3513))
- `opentelemetry-instrumentation` Allow re-raising exception when instrumentation fails
  ([#3545](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3545))
- `opentelemetry-instrumentation-aiokafka` Add instrumentation of `consumer.getmany` (batch)
  ([#3257](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3257))
  
### Deprecated

- Drop support for Python 3.8, bump baseline to Python 3.9.
([#3399](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3399))

## Version 1.33.0/0.54b0 (2025-05-09)

### Added

- `opentelemetry-instrumentation-requests` Support explicit_bucket_boundaries_advisory in duration metrics
  ([#3464](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3464))
- `opentelemetry-instrumentation-redis` Add support for redis client-specific instrumentation.
  ([#3143](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3143))

### Fixed

- `opentelemetry-instrumentation` Catch `ModuleNotFoundError` when the library is not installed
  and log as debug instead of exception
  ([#3423](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3423))
- `opentelemetry-instrumentation-asyncio` Fix duplicate instrumentation
  ([#3383](https://github.com/open-telemetry/opentelemetry-python-contrib/issues/3383))
- `opentelemetry-instrumentation-botocore` Add GenAI instrumentation for additional Bedrock models for InvokeModel API
  ([#3419](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3419))
- `opentelemetry-instrumentation` don't print duplicated conflict log error message
  ([#3432](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3432))
- `opentelemetry-instrumentation-grpc` Check for None result in gRPC
  ([#3380](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3381))
- `opentelemetry-instrumentation-[asynclick/click]` Add missing opentelemetry-instrumentation dep
  ([#3447](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3447))
- `opentelemetry-instrumentation-botocore` Capture server attributes for botocore API calls
  ([#3448](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3448))

## Version 1.32.0/0.53b0 (2025-04-10)

### Added

- `opentelemetry-instrumentation-asyncclick`: new instrumentation to trace asyncclick commands
  ([#3319](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3319))
- `opentelemetry-instrumentation-botocore` Add support for GenAI tool events using Amazon Nova models and `InvokeModel*` APIs
  ([#3385](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3385))
- `opentelemetry-instrumentation` Make auto instrumentation use the same dependency resolver as manual instrumentation does
  ([#3202](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3202))

### Fixed

- `opentelemetry-instrumentation` Fix client address is set to server address in new semconv
  ([#3354](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3354))
- `opentelemetry-instrumentation-dbapi`, `opentelemetry-instrumentation-django`,
  `opentelemetry-instrumentation-sqlalchemy`: Fix sqlcomment for non string query and composable object.
  ([#3113](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3113))
- `opentelemetry-instrumentation-grpc` Fix error when using gprc versions <= 1.50.0 with unix sockets.
  ([[#3393](https://github.com/open-telemetry/opentelemetry-python-contrib/issues/3393)])
- `opentelemetry-instrumentation-asyncio` Fix duplicate instrumentation.
  ([[#3383](https://github.com/open-telemetry/opentelemetry-python-contrib/issues/3383)])
- `opentelemetry-instrumentation-aiokafka` Fix send_and_wait method no headers kwargs error.
  ([[#3332](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3332)])

## Version 1.31.0/0.52b0 (2025-03-12)

### Added

- `opentelemetry-instrumentation-openai-v2` Update doc for OpenAI Instrumentation to support OpenAI Compatible Platforms
  ([#3279](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3279))
- `opentelemetry-instrumentation-system-metrics` Add `process` metrics and deprecated `process.runtime` prefixed ones
  ([#3250](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3250))
- `opentelemetry-instrumentation-botocore` Add support for GenAI user events and lazy initialize tracer
  ([#3258](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3258))
- `opentelemetry-instrumentation-botocore` Add support for GenAI system events
  ([#3266](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3266))
- `opentelemetry-instrumentation-botocore` Add support for GenAI choice events
  ([#3275](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3275))
- `opentelemetry-instrumentation-botocore` Add support for GenAI tool events
  ([#3302](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3302))
- `opentelemetry-instrumentation-botocore` Add support for GenAI metrics
  ([#3326](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3326))
- `opentelemetry-instrumentation` make it simpler to initialize auto-instrumentation programmatically
  ([#3273](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3273))
- Add `opentelemetry-instrumentation-vertexai>=2.0b0` to `opentelemetry-bootstrap`
  ([#3307](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3307))
- Loosen `opentelemetry-instrumentation-starlette[instruments]` specifier
  ([#3304](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3304))

### Fixed

- `opentelemetry-instrumentation-redis` Add missing entry in doc string for `def _instrument`
  ([#3247](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3247))
- `opentelemetry-instrumentation-botocore` sns-extension: Change destination name attribute
  to match topic ARN and redact phone number from attributes
  ([#3249](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3249))
- `opentelemetry-instrumentation-asyncpg` Fix fallback for empty queries.
  ([#3253](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3253))
- `opentelemetry-instrumentation` Fix a traceback in sqlcommenter when psycopg connection pooling is enabled.
  ([#3309](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3309))
- `opentelemetry-instrumentation-threading` Fix broken context typehints
  ([#3322](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3322))
- `opentelemetry-instrumentation-requests` always record span status code in duration metric
  ([#3323](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3323))

## Version 1.30.0/0.51b0 (2025-02-03)

### Added

- `opentelemetry-instrumentation-confluent-kafka` Add support for confluent-kafka <=2.7.0
  ([#3100](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3100))
- Add support to database stability opt-in in `_semconv` utilities and add tests
  ([#3111](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3111))
- `opentelemetry-instrumentation-urllib` Add `py.typed` file to enable PEP 561
  ([#3131](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3131))
- `opentelemetry-opentelemetry-pymongo` Add `py.typed` file to enable PEP 561
  ([#3136](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3136))
- `opentelemetry-opentelemetry-requests` Add `py.typed` file to enable PEP 561
  ([#3135](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3135))
- `opentelemetry-instrumentation-system-metrics` Add `py.typed` file to enable PEP 561
  ([#3132](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3132))
- `opentelemetry-opentelemetry-sqlite3` Add `py.typed` file to enable PEP 561
  ([#3133](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3133))
- `opentelemetry-instrumentation-falcon` add support version to v4
  ([#3086](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3086))
- `opentelemetry-instrumentation-falcon` Implement new HTTP semantic convention opt-in for Falcon
  ([#2790](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2790))
- `opentelemetry-instrumentation-wsgi` always record span status code to have it available in metrics
  ([#3148](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3148))
- add support to Python 3.13
  ([#3134](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3134))
- `opentelemetry-opentelemetry-wsgi` Add `py.typed` file to enable PEP 561
  ([#3129](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3129))
- `opentelemetry-util-http` Add `py.typed` file to enable PEP 561
  ([#3127](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3127))
- `opentelemetry-instrumentation-psycopg2` Add support for psycopg2-binary
  ([#3186](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3186))
- `opentelemetry-opentelemetry-botocore` Add basic support for GenAI attributes for AWS Bedrock Converse API
  ([#3161](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3161))
- `opentelemetry-opentelemetry-botocore` Add basic support for GenAI attributes for AWS Bedrock InvokeModel API
  ([#3200](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3200))
- `opentelemetry-opentelemetry-botocore` Add basic support for GenAI attributes for AWS Bedrock ConverseStream API
  ([#3204](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3204))
- `opentelemetry-opentelemetry-botocore` Add basic support for GenAI attributes for AWS Bedrock InvokeModelWithStreamResponse API
  ([#3206](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3206))
- `opentelemetry-instrumentation-pymssql` Add pymssql instrumentation
  ([#394](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/394))
- `opentelemetry-instrumentation-mysql` Add sqlcommenter support
  ([#3163](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3163))

### Fixed

- `opentelemetry-instrumentation-httpx` Fix `RequestInfo`/`ResponseInfo` type hints
  ([#3105](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3105))
- `opentelemetry-instrumentation-dbapi` Move `TracedCursorProxy` and `TracedConnectionProxy` to the module level
  ([#3068](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3068))
- `opentelemetry-instrumentation-click` Disable tracing of well-known server click commands
  ([#3174](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3174))
- `opentelemetry-instrumentation` Fix `get_dist_dependency_conflicts` if no distribution requires
  ([#3168](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3168))

### Breaking changes

- `opentelemetry-exporter-prometheus-remote-write` updated protobuf required version from 4.21 to 5.26 and regenerated protobufs
  ([#3219](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3219))
- `opentelemetry-instrumentation-sqlalchemy` including sqlcomment in `db.statement` span attribute value is now opt-in
  ([#3112](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3112))
- `opentelemetry-instrumentation-dbapi` including sqlcomment in `db.statement` span attribute value is now opt-in
  ([#3115](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3115))
- `opentelemetry-instrumentation-psycopg2`, `opentelemetry-instrumentation-psycopg`, `opentelemetry-instrumentation-mysqlclient`, `opentelemetry-instrumentation-pymysql`: including sqlcomment in `db.statement` span attribute value is now opt-in
  ([#3121](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3121))

## Version 1.29.0/0.50b0 (2024-12-11)

### Added

- `opentelemetry-instrumentation-starlette` Add type hints to the instrumentation
  ([#3045](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3045))
- `opentelemetry-distro` default to OTLP log exporter.
  ([#3042](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3042))
- `opentelemetry-instrumentation-sqlalchemy` Update unit tests to run with SQLALchemy 2
  ([#2976](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2976))
- Add `opentelemetry-instrumentation-openai-v2` to `opentelemetry-bootstrap`
  ([#2996](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2996))
- `opentelemetry-instrumentation-sqlalchemy` Add sqlcomment to `db.statement` attribute
  ([#2937](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2937))
- `opentelemetry-instrumentation-dbapi` Add sqlcomment to `db.statement` attribute
  ([#2935](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2935))
- `opentelemetry-instrumentation-dbapi` instrument_connection accepts optional connect_module
  ([#3027](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3027))
- `opentelemetry-instrumentation-mysqlclient` Add sqlcommenter support
  ([#2941](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2941))
- `opentelemetry-instrumentation-pymysql` Add sqlcommenter support
  ([#2942](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2942))
- `opentelemetry-instrumentation-click`: new instrumentation to trace click commands
  ([#2994](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2994))

### Fixed

- `opentelemetry-instrumentation-starlette`: Retrieve `meter_provider` key instead of `_meter_provider` on `_instrument`
  ([#3048](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3048))
- `opentelemetry-instrumentation-httpx`: instrument_client is a static method again
  ([#3003](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3003))
- `opentelemetry-instrumentation-system_metrics`: fix callbacks reading wrong config
  ([#3025](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3025))
- `opentelemetry-instrumentation-httpx`: Check if mount transport is none before wrap it
  ([#3022](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3022))
- Replace all instrumentor unit test `assertEqualSpanInstrumentationInfo` calls with `assertEqualSpanInstrumentationScope` calls
  ([#3037](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3037))
- `opentelemetry-instrumentation-sqlalchemy` Fixes engines from `sqlalchemy.engine_from_config` not being fully instrumented
  ([#2816](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2816))
- `opentelemetry-instrumentation-sqlalchemy`: Fix a remaining memory leak in EngineTracer
  ([#3053](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3053))
- `opentelemetry-instrumentation-sqlite3`: Update documentation on explicit cursor support of tracing
  ([#3088](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3088))

### Breaking changes

- `opentelemetry-instrumentation-sqlalchemy` teach instruments version
  ([#2971](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2971))
- Drop `opentelemetry-instrumentation-test` package from default instrumentation list
  ([#2969](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2969))
- `opentelemetry-instrumentation-httpx`: remove private unused `_InstrumentedClient` and `_InstrumentedAsyncClient` classes
  ([#3036](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3036))

## Version 1.28.0/0.49b0 (2024-11-05)

### Added

- `opentelemetry-instrumentation-openai-v2` Instrumentation for OpenAI >= 0.27.0
  ([#2759](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2759))
- `opentelemetry-instrumentation-fastapi` Add autoinstrumentation mechanism tests.
  ([#2860](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2860))
- `opentelemetry-instrumentation-aiokafka` Add instrumentor and auto instrumentation support for aiokafka
  ([#2082](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2082))
- `opentelemetry-instrumentation-redis` Add additional attributes for methods create_index and search, rename those spans
  ([#2635](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2635))
- `opentelemetry-instrumentation` Add support for string based dotted module paths in unwrap
  ([#2919](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2919))

### Fixed

- `opentelemetry-instrumentation-aiokafka` Wrap `AIOKafkaConsumer.getone()` instead of `AIOKafkaConsumer.__anext__`
  ([#2874](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2874))
- `opentelemetry-instrumentation-confluent-kafka` Fix to allow `topic` to be extracted from `kwargs` in `produce()`
  ([#2901])(https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2901)
- `opentelemetry-instrumentation-system-metrics` Update metric units to conform to UCUM conventions.
  ([#2922](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2922))
- `opentelemetry-instrumentation-celery` Don't detach context without a None token
  ([#2927](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2927))
- `opentelemetry-exporter-prometheus-remote-write`: sort labels before exporting
  ([#2940](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2940))
- `opentelemetry-instrumentation-dbapi` sqlcommenter key values created from PostgreSQL, MySQL systems
  ([#2897](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2897))
- `opentelemetry-instrumentation-system-metrics`: don't report open file descriptors on Windows
  ([#2946](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2946))

### Breaking changes

- Deprecation of pkg_resource in favor of importlib.metadata
  ([#2871](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2871))
- `opentelemetry-instrumentation` Don't fail distro loading if instrumentor raises ImportError, instead skip them
  ([#2923](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2923))
- `opentelemetry-instrumentation-httpx` Rewrote instrumentation to use wrapt instead of subclassing
  ([#2909](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2909))

## Version 1.27.0/0.48b0 (2024-08-28)

### Added

- `opentelemetry-instrumentation-kafka-python` Instrument temporary fork, kafka-python-ng inside kafka-python's instrumentation
  ([#2537](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2537))
- `opentelemetry-instrumentation-asgi`, `opentelemetry-instrumentation-fastapi` Add ability to disable internal HTTP send and receive spans
  ([#2802](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2802))
- `opentelemetry-instrumentation-asgi` Add fallback decoding for ASGI headers
  ([#2837](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2837))

### Breaking changes

- `opentelemetry-bootstrap` Remove `opentelemetry-instrumentation-aws-lambda` from the defaults instrumentations
  ([#2786](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2786))

### Fixed

- `opentelemetry-instrumentation-httpx` fix handling of async hooks
  ([#2823](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2823))
- `opentelemetry-instrumentation-system-metrics` fix `process.runtime.cpu.utilization` values to be shown in range of 0 to 1
  ([#2812](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2812))
- `opentelemetry-instrumentation-fastapi` fix `fastapi` auto-instrumentation by removing `fastapi-slim` support, `fastapi-slim` itself is discontinued from maintainers
  ([#2783](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2783))
- `opentelemetry-instrumentation-aws-lambda` Avoid exception when a handler is not present.
  ([#2750](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2750))
- `opentelemetry-instrumentation-django` Fix regression - `http.target` re-added back to old semconv duration metrics
  ([#2746](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2746))
- `opentelemetry-instrumentation-asgi` do not set `url.full` attribute for server spans
  ([#2735](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2735))
- `opentelemetry-instrumentation-grpc` Fixes the issue with the gRPC instrumentation not working with the 1.63.0 and higher version of gRPC
  ([#2483](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2484))
- `opentelemetry-instrumentation-aws-lambda` Fixing w3c baggage support
  ([#2589](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2589))
- `opentelemetry-instrumentation-celery` propagates baggage
  ([#2385](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2385))
- `opentelemetry-instrumentation-asyncio` Fixes async generator coroutines not being awaited
  ([#2792](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2792))
- `opentelemetry-instrumentation-tornado` Handle http client exception and record exception info into span
  ([#2563](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2563))
- `opentelemetry-instrumentation` fix `http.host` new http semantic convention mapping to depend on `kind` of span
  ([#2814](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2814))
- `opentelemetry-instrumentation` Fix the description of `http.server.duration` and `http.server.request.duration`
  ([#2753](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2753))
- `opentelemetry-instrumentation-grpc` Fix grpc supported version
  ([#2845](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2845))
- `opentelemetry-instrumentation-asyncio` fix `AttributeError` in
  `AsyncioInstrumentor.trace_to_thread` when `func` is a `functools.partial` instance
  ([#2911](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2911))

## Version 1.26.0/0.47b0 (2024-07-23)

### Added

- `opentelemetry-instrumentation-flask` Add `http.route` and `http.target` to metric attributes
  ([#2621](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2621))
- `opentelemetry-instrumentation-aws-lambda` Enable global propagator for AWS instrumentation
  ([#2708](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2708))
- `opentelemetry-instrumentation-sklearn` Deprecated the sklearn instrumentation
  ([#2708](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2708))
- `opentelemetry-instrumentation-pyramid` Record exceptions raised when serving a request
  ([#2622](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2622))
- `opentelemetry-sdk-extension-aws` Add AwsXrayLambdaPropagator
  ([#2573](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2573))
- `opentelemetry-instrumentation-confluent-kafka` Add support for version 2.4.0 of confluent_kafka
  ([#2616](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2616))
- `opentelemetry-instrumentation-asyncpg` Add instrumentation to cursor based queries
  ([#2501](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2501))
- `opentelemetry-instrumentation-confluent-kafka` Add support for produce purge
  ([#2638](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2638))
- `opentelemetry-instrumentation-asgi` Implement new semantic convention opt-in with stable http semantic conventions
  ([#2610](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2610))
- `opentelemetry-instrumentation-fastapi` Implement new semantic convention opt-in with stable http semantic conventions
  ([#2682](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2682))
- `opentelemetry-instrumentation-httpx` Implement new semantic convention opt-in migration with stable http semantic conventions
  ([#2631](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2631))
- `opentelemetry-instrumentation-system-metrics` Permit to use psutil 6.0+.
  ([#2630](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2630))
- `opentelemetry-instrumentation-system-metrics` Add support for capture open file descriptors
  ([#2652](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2652))
- `opentelemetry-instrumentation-httpx` Add support for instrument client with proxy
  ([#2664](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2664))
- `opentelemetry-instrumentation-aiohttp-client` Implement new semantic convention opt-in migration
  ([#2673](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2673))
- `opentelemetry-instrumentation-django` Add `http.target` to Django duration metric attributes
  ([#2624](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2624))
- `opentelemetry-instrumentation-urllib3` Implement new semantic convention opt-in migration
  ([#2715](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2715))
- `opentelemetry-instrumentation-django` Implement new semantic convention opt-in with stable http semantic conventions
  ([#2714](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2714))
- `opentelemetry-instrumentation-urllib` Implement new semantic convention opt-in migration
  ([#2736](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2736))

### Breaking changes

- `opentelemetry-instrumentation-asgi`, `opentelemetry-instrumentation-fastapi`, `opentelemetry-instrumentation-starlette` Use `tracer` and `meter` of originating components instead of one from `asgi` middleware
  ([#2580](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2580))
- Populate `{method}` as `HTTP` on `_OTHER` methods from scope for `asgi` middleware
  ([#2610](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2610))
- Populate `{method}` as `HTTP` on `_OTHER` methods from scope for `fastapi` middleware
  ([#2682](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2682))
- `opentelemetry-instrumentation-urllib3` Populate `{method}` as `HTTP` on `_OTHER` methods for span name
  ([#2715](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2715))
- Populate `{method}` as `HTTP` on `_OTHER` methods from scope for `fastapi` instrumentation
  ([#2682](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2682))
- Populate `{method}` as `HTTP` on `_OTHER` methods from scope for `django` middleware
  ([#2714](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2714))
- Populate `{method}` as `HTTP` on `_OTHER` methods from scope for `urllib` instrumentation
  ([#2736](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2736))
- `opentelemetry-instrumentation-httpx`, `opentelemetry-instrumentation-aiohttp-client`,
  `opentelemetry-instrumentation-requests` Populate `{method}` as `HTTP` on `_OTHER` methods
  ([#2726](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2726))
- `opentelemetry-instrumentation-fastapi` Add dependency support for fastapi-slim
  ([#2702](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2702))
- `opentelemetry-instrumentation-urllib3` improve request_hook, replacing `headers` and `body` parameters with a single `request_info: RequestInfo` parameter that now contains the `method` and `url` ([#2711](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2711))

### Fixed

- Handle `redis.exceptions.WatchError` as a non-error event in redis instrumentation
  ([#2668](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2668))
- `opentelemetry-instrumentation-httpx` Ensure httpx.get or httpx.request like methods are instrumented
  ([#2538](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2538))
- Add Python 3.12 support
  ([#2572](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2572))
- `opentelemetry-instrumentation-aiohttp-server`, `opentelemetry-instrumentation-httpx` Ensure consistently use of suppress_instrumentation utils
  ([#2590](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2590))
- Reference symbols from generated semantic conventions
  ([#2611](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2611))
- `opentelemetry-instrumentation-psycopg` Bugfix: Handle empty statement.
  ([#2644](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2644))
- `opentelemetry-instrumentation-confluent-kafka` Confluent Kafka: Ensure consume span is ended when consumer is closed
  ([#2640](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2640))
- `opentelemetry-instrumentation-asgi` Fix generation of `http.target` and `http.url` attributes for ASGI apps
  using sub apps
  ([#2477](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2477))
- `opentelemetry-instrumentation-aws-lambda` Bugfix: AWS Lambda event source key incorrect for SNS in instrumentation library.
  ([#2612](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2612))
- `opentelemetry-instrumentation-asyncio` instrumented `asyncio.wait_for` properly raises `asyncio.TimeoutError` as expected
  ([#2637](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2637))
- `opentelemetry-instrumentation-django` Handle exceptions from request/response hooks
  ([#2153](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2153))
- `opentelemetry-instrumentation-asgi` Removed `NET_HOST_NAME` AND `NET_HOST_PORT` from active requests count attribute
  ([#2610](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2610))
- `opentelemetry-instrumentation-asgi` Bugfix: Middleware did not set status code attribute on duration metrics for non-recording spans.
  ([#2627](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2627))
- `opentelemetry-instrumentation-mysql` Add support for `mysql-connector-python` v9
  ([#2751](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2751))

## Version 1.25.0/0.46b0 (2024-05-31)

### Breaking changes

- Add return statement to Confluent kafka Producer poll() and flush() calls when instrumented by ConfluentKafkaInstrumentor().instrument_producer() ([#2527](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2527))
- Rename `type` attribute to `asgi.event.type` in `opentelemetry-instrumentation-asgi`
  ([#2300](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2300))
- Rename AwsLambdaInstrumentor span attributes `faas.id` to `cloud.resource_id`, `faas.execution` to `faas.invocation_id`
  ([#2372](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2372))
- Drop support for instrumenting elasticsearch client < 6
  ([#2422](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2422))
- `opentelemetry-instrumentation-wsgi` Add `http.method` to `span.name`
  ([#2425](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2425))
- `opentelemetry-instrumentation-flask` Add `http.method` to `span.name`
  ([#2454](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2454))
- Record repeated HTTP headers in lists, rather than a comma separate strings for ASGI based web frameworks
  ([#2361](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2361))
- ASGI, FastAPI, Starlette: provide both send and receive hooks with `scope` and `message` for internal spans
- ([#2546](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2546))

### Added

- `opentelemetry-sdk-extension-aws` Register AWS resource detectors under the
  `opentelemetry_resource_detector` entry point
  ([#2382](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2382))
- `opentelemetry-instrumentation-wsgi` Implement new semantic convention opt-in with stable http semantic conventions
  ([#2425](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2425))
- `opentelemetry-instrumentation-flask` Implement new semantic convention opt-in with stable http semantic conventions
  ([#2454](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2454))
- `opentelemetry-instrumentation-threading` Initial release for threading
  ([#2253](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2253))
- `opentelemetry-instrumentation-pika` Instrumentation for `channel.consume()` (supported
  only for global, non channel specific instrumentation)
  ([#2397](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2397))
- `opentelemetry-processor-baggage` Initial release
  ([#2436](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2436))
- `opentelemetry-processor-baggage` Add baggage key predicate
  ([#2535](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2535))

### Fixed

- `opentelemetry-instrumentation-dbapi` Fix compatibility with Psycopg3 to extract libpq build version
  ([#2500](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2500))
- `opentelemetry-instrumentation-grpc` AioClientInterceptor should propagate with a Metadata object
  ([#2363](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2363))
- `opentelemetry-instrumentation-boto3sqs` Instrument Session and resource
  ([#2161](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2161))
- `opentelemetry-instrumentation-aws-lambda` Fix exception handling for events with requestContext
  ([#2418](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2418))
- Use sqlalchemy version in sqlalchemy commenter instead of opentelemetry library version
  ([#2404](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2404))
- `opentelemetry-instrumentation-asyncio` Check for cancelledException in the future
  ([#2461](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2461))
- Remove SDK dependency from opentelemetry-instrumentation-grpc
  ([#2474](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2474))
- `opentelemetry-instrumentation-elasticsearch` Improved support for version 8
  ([#2420](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2420))
- `opentelemetry-instrumentation-elasticsearch` Disabling instrumentation with native OTel support enabled
  ([#2524](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2524))
- `opentelemetry-instrumentation-asyncio` Check for **name** attribute in the coroutine
  ([#2521](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2521))
- `opentelemetry-instrumentation-requests` Fix wrong time unit for duration histogram
  ([#2553](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2553))
- `opentelemetry-util-http` Preserve brackets around literal IPv6 hosts ([#2552](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2552))
- `opentelemetry-util-redis` Fix net peer attribute for unix socket connection ([#2493](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2493))

## Version 1.24.0/0.45b0 (2024-03-28)

### Added

- `opentelemetry-instrumentation-psycopg` Async Instrumentation for psycopg 3.x
  ([#2146](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2146))

### Fixed

- `opentelemetry-instrumentation-celery` Allow Celery instrumentation to be installed multiple times
  ([#2342](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2342))
- Align gRPC span status codes to OTEL specification
  ([#1756](https://github.com/open-telemetry/opentelemetry-python-contrib/issues/1756))
- `opentelemetry-instrumentation-flask` Add importlib metadata default for deprecation warning flask version
  ([#2297](https://github.com/open-telemetry/opentelemetry-python-contrib/issues/2297))
- Ensure all http.server.duration metrics have the same description
  ([#2151](https://github.com/open-telemetry/opentelemetry-python-contrib/issues/2298))
- Fix regression in httpx `request.url` not being of type `httpx.URL` after `0.44b0`
  ([#2359](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2359))
- Avoid losing repeated HTTP headers
  ([#2266](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2266))
- `opentelemetry-instrumentation-elasticsearch` Don't send bulk request body as db statement
  ([#2355](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2355))
- AwsLambdaInstrumentor sets `cloud.account.id` span attribute
  ([#2367](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2367))

### Added

- `opentelemetry-instrumentation-fastapi` Add support for configuring header extraction via runtime constructor parameters
  ([#2241](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2241))

## Version 1.23.0/0.44b0 (2024-02-23)

- Drop support for 3.7
  ([#2151](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2151))
- `opentelemetry-resource-detector-azure` Added 10s timeout to VM Resource Detector
  ([#2119](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2119))
- `opentelemetry-instrumentation-asyncpg` Allow AsyncPGInstrumentor to be instantiated multiple times
  ([#1791](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1791))
- `opentelemetry-instrumentation-confluent-kafka` Add support for higher versions until 2.3.0 of confluent_kafka
  ([#2132](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2132))
- `opentelemetry-resource-detector-azure` Changed timeout to 4 seconds due to [timeout bug](https://github.com/open-telemetry/opentelemetry-python/issues/3644)
  ([#2136](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2136))
- `opentelemetry-resource-detector-azure` Suppress instrumentation for `urllib` call
  ([#2178](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2178))
- AwsLambdaInstrumentor handles and re-raises function exception
  ([#2245](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2245))

### Added

- `opentelemetry-instrumentation-psycopg` Initial release for psycopg 3.x
- `opentelemetry-instrumentation-asgi` Add support for configuring ASGI middleware header extraction via runtime constructor parameters
  ([#2026](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2026))

## Version 1.22.0/0.43b0 (2023-12-14)

### Added

- `opentelemetry-instrumentation-asyncio` Add support for asyncio
  ([#1919](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1943))
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
- `opentelemetry-instrumentation-django` - Add option to add Opentelemetry middleware at specific position in middleware chain
  ([#2912]https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2912)

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
- `opentelemetry-instrumentation-redis` Add `sanitize_query` config option to allow query sanitization. ([#1572](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1572))
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
- `opentelemetry-instrumentation-grpc` Fix code()/details() of \_OpentelemetryServicerContext.
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
- `opentelemetry-instrumentation-pymysql` Fix dbapi connection instrument wrapper has no \_sock member.
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
- Add \_is_opentelemetry_instrumented check in \_InstrumentedFastAPI class
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

- `opentelemetry-instrumentation-pyramid` Fixed which package is the correct caller in \_traced_init.
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
- `opentelemetry-instrumentation-grpc` added `trailing_metadata` to \_OpenTelemetryServicerContext.
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

- `opentelemetry-instrumentation-aws-lambda` Adds support for configurable flush timeout via `OTEL_INSTRUMENTATION_AWS_LAMBDA_FLUSH_TIMEOUT` property. ([#825](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/825))
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

### Removed

- Removing support for Python 3.5
  ([#374](https://github.com/open-telemetry/opentelemetry-python/pull/374))

## Version 0.18b0 (2021-02-16)

### Added

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

## Version 0.17b0 (2021-01-20)

### Added

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

## Version 0.16b0 (2020-11-25)

### Added

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

## Version 0.15b0 (2020-11-02)

### Added

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

## Version 0.14b0 (2020-10-13)

### Added

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

## Version 0.13b0 (2020-09-17)

### Added

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

### Removed

- Drop support for Python 3.4
  ([#1099](https://github.com/open-telemetry/opentelemetry-python/pull/1099))

## Version 0.12b0 (2020-08-14)

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

## Version 0.11b0 (2020-07-28)

### Added

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

## Version 0.9b0 (2020-06-10)

### Added

- `opentelemetry-ext-pyramid` Initial release
- `opentelemetry-ext-boto` Initial release
- `opentelemetry-ext-botocore` Initial release
- `opentelemetry-ext-system-metrics` Initial release
  (https://github.com/open-telemetry/opentelemetry-python/pull/652)

## Version 0.8b0 (2020-05-27)

### Added

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

## Version 0.7b1 (2020-05-12)

### Added

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

## Version 0.6b0 (2020-03-30)

### Added

- `opentelemetry-ext-flask` Add an entry_point to be usable in auto-instrumentation
  ([#327](https://github.com/open-telemetry/opentelemetry-python/pull/327))
- `opentelemetry-ext-grpc` Add gRPC integration
  ([#476](https://github.com/open-telemetry/opentelemetry-python/pull/476))

## Version 0.5b0 (2020-03-16)

## Version 0.4a0 (2020-02-21)

### Added

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

## Version 0.3a0 (2019-12-11)

### Added

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

## Version 0.1a0 (2019-09-30)

### Added

- `opentelemetry-ext-wsgi` Initial release
- `opentelemetry-ext-http-requests` Initial release

- Drop support for 3.7
  ([#2151](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2151))
- `opentelemetry-resource-detector-azure` Added 10s timeout to VM Resource Detector
  ([#2119](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2119))
- `opentelemetry-instrumentation-asyncpg` Allow AsyncPGInstrumentor to be instantiated multiple times
  ([#1791](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/1791))
- `opentelemetry-instrumentation-confluent-kafka` Add support for higher versions until 2.3.0 of confluent_kafka
  ([#2132](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2132))
- `opentelemetry-resource-detector-azure` Changed timeout to 4 seconds due to [timeout bug](https://github.com/open-telemetry/opentelemetry-python/issues/3644)
  ([#2136](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2136))
- `opentelemetry-resource-detector-azure` Suppress instrumentation for `urllib` call
  ([#2178](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2178))
- AwsLambdaInstrumentor handles and re-raises function exception ([#2245](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2245))
