# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased](https://github.com/ox-eye/oxeye_opentelemetry-python/compare/v1.4.0-0.23b0...HEAD)

## [1.4.0-0.23b0](https://github.com/ox-eye/oxeye_opentelemetry-python/releases/tag/v1.4.0-0.23b0) - 2021-07-19



### Removed
- Move `oxeye_opentelemetry-instrumentation` to the core repo.
  ([#595](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/595))

### Changed
- `oxeye_opentelemetry-instrumentation-tornado` properly instrument work done in tornado on_finish method.
  ([#499](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/499))
- `oxeye_opentelemetry-instrumentation` Fixed cases where trying to use an instrumentation package without the
  target library was crashing auto instrumentation agent.
  ([#530](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/530))
- Fix weak reference error for pyodbc cursor in SQLAlchemy instrumentation.
  ([#469](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/469))
- Implemented specification that HTTP span attributes must not contain username and password.
  ([#538](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/538))
- Changed the psycopg2-binary to psycopg2 as dependency in production
  ([#543](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/543))
- Implement consistent way of checking if instrumentation is already active
  ([#549](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/549))
- Require aiopg to be less than 1.3.0
  ([#560](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/560))
- `oxeye_opentelemetry-instrumentation-django` Migrated Django middleware to new-style.
  ([#533](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/533))
- Updating dependency for oxeye_opentelemetry api/sdk packages to support major version instead
  of pinning to specific versions.
  ([#567](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/567))
- `oxeye_opentelemetry-instrumentation-grpc` Respect the suppress instrumentation in gRPC client instrumentor
  ([#559](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/559))
- `oxeye_opentelemetry-instrumentation-grpc` Fixed asynchonous unary call traces
  ([#536](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/536))
- `oxeye_opentelemetry-sdk-extension-aws` Update AWS entry points to match spec
  ([#566](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/566))
- Include Flask 2.0 as compatible with existing flask instrumentation
  ([#545](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/545))
- `openelemetry-sdk-extension-aws` Take a dependency on `oxeye_opentelemetry-sdk`
  ([#558](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/558))
- Change `oxeye_opentelemetry-instrumentation-httpx` to replace `client` classes with instrumented versions.
  ([#577](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/577))
- `oxeye_opentelemetry-instrumentation-requests` Fix potential `AttributeError` when `requests`
  is used with a custom transport adapter.
  ([#562](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/562))
- `oxeye_opentelemetry-instrumentation-django` Fix AttributeError: ResolverMatch object has no attribute route
  ([#581](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/581))
- `oxeye_opentelemetry-instrumentation-botocore` Suppress botocore downstream instrumentation like urllib3
  ([#563](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/563))
- `oxeye_opentelemetry-exporter-datadog` Datadog exporter should not use `unknown_service` as fallback resource service name.
  ([#570](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/570))

### Added
- `oxeye_opentelemetry-instrumentation-httpx` Add `httpx` instrumentation
  ([#461](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/461))

## [0.22b0](https://github.com/ox-eye/oxeye_opentelemetry-python/releases/tag/v1.3.0-0.22b0) - 2021-06-01

### Changed
- `oxeye_opentelemetry-bootstrap` not longer forcibly removes and re-installs libraries and their instrumentations.
  This means running bootstrap will not auto-upgrade existing dependencies and as a result not cause dependency
  conflicts.
  ([#514](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/514))
- `oxeye_opentelemetry-instrumentation-asgi` Set the response status code on the server span
  ([#478](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/478))
- `oxeye_opentelemetry-instrumentation-tornado` Fixed cases where description was used with non-
  error status code when creating Status objects.
  ([#504](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/504))
- `oxeye_opentelemetry-instrumentation-asgi` Fix instrumentation default span name.
  ([#418](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/418))
- Propagators use the root context as default for `extract` and do not modify
  the context if extracting from carrier does not work.
  ([#488](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/488))

### Added
- `oxeye_opentelemetry-instrumentation-botocore` now supports
  context propagation for lambda invoke via Payload embedded headers.
  ([#458](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/458))
- Added support for CreateKey functionality.
  ([#502](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/502))

## [0.21b0](https://github.com/ox-eye/oxeye_opentelemetry-python/releases/tag/v1.2.0-0.21b0) - 2021-05-11

### Changed
- Instrumentation packages don't specify the libraries they instrument as dependencies
  anymore. Instead, they verify the correct version of libraries are installed at runtime.
  ([#475](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/475))
- `oxeye_opentelemetry-propagator-ot-trace` Use `TraceFlags` object in `extract`
  ([#472](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/472))
- Set the `traced_request_attrs` of FalconInstrumentor by an argument correctly.
  ([#473](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/473))
- Enable passing explicit urls to exclude in instrumentation in FastAPI
  ([#486](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/486))
- Distros can now implement `load_instrumentor(EntryPoint)` method to customize instrumentor
  loading behaviour.
  ([#480](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/480))
- Fix entrypoint for ottrace propagator
  ([#492](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/492))

### Added

- Move `oxeye_opentelemetry-instrumentation` from core repository
  ([#465](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/465))

## [0.20b0](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/releases/tag/v0.20b0) - 2021-04-20

### Changed

- Restrict DataDog exporter's `ddtrace` dependency to known working versions.
  ([#400](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/400))
- GRPC instrumentation now correctly injects trace context into outgoing requests.
  ([#392](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/39))
- Publish `oxeye_opentelemetry-propagator-ot-trace` package as a part of the release process
  ([#387](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/387))
- Update redis instrumentation to follow semantic conventions
  ([#403](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/403))
- Update instrumentations to use tracer_provider for creating tracer if given, otherwise use global tracer provider
  ([#402](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/402))
- `oxeye_opentelemetry-instrumentation-wsgi` Replaced `name_callback` with `request_hook`
  and `response_hook` callbacks.
  ([#424](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/424))
- Update gRPC instrumentation to better wrap server context
  ([#420](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/420))
- `oxeye_opentelemetry-instrumentation-redis` Fix default port KeyError and Wrong Attribute name (net.peer.ip -> net.peer.port)
  ([#265](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/265))
- `oxeye_opentelemetry-instrumentation-asyncpg` Fix default port KeyError and Wrong Attribute name (net.peer.ip -> net.peer.port)
  ([#265](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/265))

### Added

- `oxeye_opentelemetry-instrumentation-urllib3` Add urllib3 instrumentation
  ([#299](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/299))

- `oxeye_opentelemetry-instrumentation-flask` Added `request_hook` and `response_hook` callbacks.
  ([#416](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/416))

- `oxeye_opentelemetry-instrumenation-django` now supports request and response hooks.
  ([#407](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/407))
- `oxeye_opentelemetry-instrumentation-falcon` FalconInstrumentor now supports request/response hooks.
  ([#415](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/415))
- `oxeye_opentelemetry-instrumentation-tornado` Add request/response hooks.
  ([#426](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/426))
- `oxeye_opentelemetry-exporter-datadog` Add parsing exception events for error tags.
  ([#459](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/459))
- `oxeye_opentelemetry-instrumenation-django` now supports trace response headers.
  ([#436](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/436))
- `oxeye_opentelemetry-instrumenation-tornado` now supports trace response headers.
  ([#436](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/436))
- `oxeye_opentelemetry-instrumenation-pyramid` now supports trace response headers.
  ([#436](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/436))
- `oxeye_opentelemetry-instrumenation-falcon` now supports trace response headers.
  ([#436](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/436))
- `oxeye_opentelemetry-instrumenation-flask` now supports trace response headers.
  ([#436](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/436))
- `oxeye_opentelemetry-instrumentation-grpc` Keep client interceptor in sync with grpc client interceptors.
  ([#442](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/442))

### Removed

- Remove `http.status_text` from span attributes
  ([#406](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/406))

## [0.19b0](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/releases/tag/v0.19b0) - 2021-03-26

- Implement context methods for `_InterceptorChannel`
  ([#363](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/363))

### Changed

- Rename `IdsGenerator` to `IdGenerator`
  ([#350](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/350))
- `oxeye_opentelemetry-exporter-datadog` Fix warning when DatadogFormat encounters a request with
  no DD_ORIGIN headers ([#368](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/368)).
- `oxeye_opentelemetry-instrumentation-aiopg` Fix multiple nested spans when
  `aiopg.pool` is used
  ([#336](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/381)).
- Updated instrumentations to use `oxeye_opentelemetry.trace.use_span` instead of `Tracer.use_span()`
  ([#364](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/364))
- `oxeye_opentelemetry-propagator-ot-trace` Do not throw an exception when headers are not present
  ([#378](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/378))
- `oxeye_opentelemetry-instrumentation-wsgi` Reimplement `keys` method to return actual keys from the carrier instead of an empty list.
  ([#379](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/379))
- `oxeye_opentelemetry-instrumentation-sqlalchemy` Fix multithreading issues in recording spans from SQLAlchemy
  ([#315](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/315))
- Make getters and setters optional
  ([#372](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/372))

### Removed

- Removing support for Python 3.5
  ([#374](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/374))

## [0.18b0](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/releases/tag/v0.18b0) - 2021-02-16

### Added

- `oxeye_opentelemetry-propagator-ot-trace` Add OT Trace Propagator
  ([#302](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/302))
- `oxeye_opentelemetry-instrumentation-logging` Added logging instrumentation to enable log - trace correlation.
  ([#345](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/345))

### Removed

- Remove `component` span attribute in instrumentations.
  `oxeye_opentelemetry-instrumentation-aiopg`, `oxeye_opentelemetry-instrumentation-dbapi` Remove unused `database_type` parameter from `trace_integration` function.
  ([#301](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/301))
- `oxeye_opentelemetry-instrumentation-asgi` Return header values using case insensitive keys
  ([#308](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/308))
- Remove metrics from all instrumentations
  ([#312](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/312))
- `oxeye_opentelemetry-instrumentation-boto` updated to set span attributes instead of overriding the resource.
  ([#310](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/310))
- `oxeye_opentelemetry-instrumentation-grpc` Fix issue tracking child spans in streaming responses
  ([#260](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/260))
- `oxeye_opentelemetry-instrumentation-grpc` Updated client attributes, added tests, fixed examples, docs
  ([#269](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/269))

## [0.17b0](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/releases/tag/v0.17b0) - 2021-01-20

### Added

- `oxeye_opentelemetry-instrumentation-sqlalchemy` Ensure spans have kind set to "CLIENT"
  ([#278](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/278))
- `oxeye_opentelemetry-instrumentation-celery` Add support for Celery version 5.x
  ([#266](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/266))
- `oxeye_opentelemetry-instrumentation-urllib` Add urllib instrumentation
  ([#222](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/222))
- `oxeye_opentelemetry-exporter-datadog` Add fields method
  ([#226](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/226))
- `oxeye_opentelemetry-sdk-extension-aws` Add method to return fields injected by propagator
  ([#226](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/226))
- `oxeye_opentelemetry-exporter-prometheus-remote-write` Prometheus Remote Write Exporter Setup
  ([#180](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/180))
- `oxeye_opentelemetry-exporter-prometheus-remote-write` Add Exporter constructor validation methods in Prometheus Remote Write Exporter
  ([#206](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/206))
- `oxeye_opentelemetry-exporter-prometheus-remote-write` Add conversion to TimeSeries methods in Prometheus Remote Write Exporter
  ([#207](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/207))
- `oxeye_opentelemetry-exporter-prometheus-remote-write` Add request methods to Prometheus Remote Write Exporter
  ([#212](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/212))
- `oxeye_opentelemetry-instrumentation-fastapi` Added support for excluding some routes with env var `OTEL_PYTHON_FASTAPI_EXCLUDED_URLS`
  ([#237](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/237))
- `oxeye_opentelemetry-instrumentation-starlette` Added support for excluding some routes with env var `OTEL_PYTHON_STARLETTE_EXCLUDED_URLS`
  ([#237](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/237))
- Add Prometheus Remote Write Exporter integration tests in oxeye_opentelemetry-docker-tests
  ([#216](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/216))
- `oxeye_opentelemetry-instrumentation-grpc` Add tests for grpc span attributes, grpc `abort()` conditions
  ([#236](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/236))
- Add README and example app for Prometheus Remote Write Exporter
  ([#227](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/227]))
- `oxeye_opentelemetry-instrumentation-botocore` Adds a field to report the number of retries it take to complete an API call
  ([#275](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/275))
- `oxeye_opentelemetry-instrumentation-requests` Use instanceof to check if responses are valid Response objects
  ([#273](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/273))

### Changed

- Fix broken links to project ([#413](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/413))
- `oxeye_opentelemetry-instrumentation-asgi`, `oxeye_opentelemetry-instrumentation-wsgi` Return `None` for `CarrierGetter` if key not found
  ([#233](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/233))
- `oxeye_opentelemetry-instrumentation-grpc` Comply with updated spec, rework tests
  ([#236](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/236))
- `oxeye_opentelemetry-instrumentation-asgi`, `oxeye_opentelemetry-instrumentation-falcon`, `oxeye_opentelemetry-instrumentation-flask`, `oxeye_opentelemetry-instrumentation-pyramid`, `oxeye_opentelemetry-instrumentation-wsgi` Renamed `host.port` attribute to `net.host.port`
  ([#242](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/242))
- `oxeye_opentelemetry-instrumentation-flask` Do not emit a warning message for request contexts created with `app.test_request_context`
  ([#253](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/253))
- `oxeye_opentelemetry-instrumentation-requests`, `oxeye_opentelemetry-instrumentation-urllib` Fix span name callback parameters
  ([#259](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/259))
- `oxeye_opentelemetry-exporter-datadog` Fix unintentional type change of span trace flags
  ([#261](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/261))
- `oxeye_opentelemetry-instrumentation-aiopg` Fix AttributeError `__aexit__` when `aiopg.connect` and `aio[g].create_pool` used with async context manager
  ([#235](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/235))
- `oxeye_opentelemetry-exporter-datadog` `oxeye_opentelemetry-sdk-extension-aws` Fix reference to ids_generator in sdk
  ([#283](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/283))
- `oxeye_opentelemetry-instrumentation-sqlalchemy` Use SQL operation and DB name as span name.
  ([#254](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/254))
- `oxeye_opentelemetry-instrumentation-dbapi`, `TracedCursor` replaced by `CursorTracer`
  ([#246](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/246))
- `oxeye_opentelemetry-instrumentation-psycopg2`, Added support for psycopg2 registered types.
  ([#246](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/246))
- `oxeye_opentelemetry-instrumentation-dbapi`, `oxeye_opentelemetry-instrumentation-psycopg2`, `oxeye_opentelemetry-instrumentation-mysql`, `oxeye_opentelemetry-instrumentation-pymysql`, `oxeye_opentelemetry-instrumentation-aiopg` Use SQL command name as the span operation name instead of the entire query.
  ([#246](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/246))
- Update TraceState to adhere to specs
  ([#276](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/276))

### Removed

- Remove Configuration
  ([#285](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/285))

## [0.16b1](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/releases/tag/v0.16b1) - 2020-11-26

## [0.16b0](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/releases/tag/v0.16b0) - 2020-11-25

### Added

- `oxeye_opentelemetry-instrumentation-flask` Add span name callback
  ([#152](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/152))
- `oxeye_opentelemetry-sdk-extension-aws` Add AWS X-Ray Ids Generator Entry Point
  ([#201](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/201))
- `oxeye_opentelemetry-sdk-extension-aws` Fix typo for installing OTel SDK in docs
  ([#200](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/200))
- `oxeye_opentelemetry-sdk-extension-aws` Import missing components for docs
  ([#198](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/198))
- `oxeye_opentelemetry-sdk-extension-aws` Provide components needed to Configure OTel SDK for Tracing with AWS X-Ray
  ([#130](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/130))
- `oxeye_opentelemetry-instrumentation-sklearn` Initial release
  ([#151](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/151))
- `oxeye_opentelemetry-instrumentation-requests` Add span name callback
  ([#158](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/158))
- `oxeye_opentelemetry-instrumentation-botocore` Add propagator injection for botocore calls
  ([#181](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/181))

### Changed

- `oxeye_opentelemetry-instrumentation-pymemcache` Update pymemcache instrumentation to follow semantic conventions
  ([#183](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/183))
- `oxeye_opentelemetry-instrumentation-redis` Update redis instrumentation to follow semantic conventions
  ([#184](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/184))
- `oxeye_opentelemetry-instrumentation-pymongo` Update pymongo instrumentation to follow semantic conventions
  ([#203](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/203))
- `oxeye_opentelemetry-instrumentation-sqlalchemy` Update sqlalchemy instrumentation to follow semantic conventions
  ([#202](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/202))
- `oxeye_opentelemetry-instrumentation-botocore` Make botocore instrumentation check if instrumentation has been suppressed
  ([#182](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/182))
- `oxeye_opentelemetry-instrumentation-botocore` Botocore SpanKind as CLIENT and modify existing traced attributes
  ([#150](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/150))
- `oxeye_opentelemetry-instrumentation-dbapi` Update dbapi and its dependant instrumentations to follow semantic conventions
  ([#195](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/195))
- `oxeye_opentelemetry-instrumentation-dbapi` Stop capturing query parameters by default
  ([#156](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/156))
- `oxeye_opentelemetry-instrumentation-asyncpg` Update asyncpg instrumentation to follow semantic conventions
  ([#188](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/pull/188))
- `oxeye_opentelemetry-instrumentation-grpc` Update protobuf versions
  ([#1356](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/1356))

## [0.15b0](https://github.com/ox-eye/oxeye_opentelemetry-python-contrib/releases/tag/v0.15b0) - 2020-11-02

### Added

- `oxeye_opentelemetry-instrumentation-requests` Add support for tracking http metrics
  ([#1230](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/1230))
- `oxeye_opentelemetry-instrumentation-django` Added capture of http.route
  ([#1226](https://github.com/ox-eye/oxeye_opentelemetry-python/issues/1226))
- `oxeye_opentelemetry-instrumentation-django` Add support for tracking http metrics
  ([#1230](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/1230))

### Changed

- `oxeye_opentelemetry-exporter-datadog` Make `SpanProcessor.on_start` accept parent Context
  ([#1251](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/1251))
- `oxeye_opentelemetry-instrumentation-flask` Use `url.rule` instead of `request.endpoint` for span name
  ([#1260](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/1260))
- `oxeye_opentelemetry-instrumentation-django` Django instrumentation is now enabled by default but can be disabled by setting `OTEL_PYTHON_DJANGO_INSTRUMENT` to `False`
  ([#1239](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/1239))
- `oxeye_opentelemetry-instrumentation-django` Bugfix use request.path replace request.get_full_path(). It will get correct span name
  ([#1309](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/1309#))
- `oxeye_opentelemetry-instrumentation-django` Record span status and http.status_code attribute on exception
  ([#1257](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/1257))
- `oxeye_opentelemetry-instrumentation-grpc` Rewrite gRPC server interceptor
  ([#1171](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/1171))

## [0.14b0](https://github.com/ox-eye/oxeye_opentelemetry-python/releases/tag/v0.14b0) - 2020-10-13

### Added

- `oxeye_opentelemetry-exporter-datadog` Add support for span resource labels and service name
- `oxeye_opentelemetry-instrumentation-celery` Span operation names now include the task type.
  ([#1135](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/1135))
- `oxeye_opentelemetry-instrumentation-celery` Added automatic context propagation.
  ([#1135](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/1135))
- `oxeye_opentelemetry-instrumentation-falcon` Added support for `OTEL_PYTHON_FALCON_TRACED_REQUEST_ATTRS`
  ([#1158](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/1158))
- `oxeye_opentelemetry-instrumentation-tornado` Added support for `OTEL_PYTHON_TORNADO_TRACED_REQUEST_ATTRS`
  ([#1178](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/1178))
- `oxeye_opentelemetry-instrumentation-django` Added support for `OTEL_PYTHON_DJANGO_TRACED_REQUEST_ATTRS`
  ([#1154](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/1154))

### Changed

- `oxeye_opentelemetry-instrumentation-pymongo` Cast PyMongo commands as strings
  ([#1132](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/1132))
- `oxeye_opentelemetry-instrumentation-system-metrics` Fix issue when specific metrics are not available in certain OS
  ([#1207](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/1207))
- `oxeye_opentelemetry-instrumentation-pymysql` Bumped version from 0.9.3 to 0.10.1
  ([#1228](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/1228))
- `oxeye_opentelemetry-instrumentation-django` Changed span name extraction from request to comply semantic convention
  ([#992](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/992))

## [0.13b0](https://github.com/ox-eye/oxeye_opentelemetry-python/releases/tag/v0.13b0) - 2020-09-17

### Added

- `oxeye_opentelemetry-instrumentation-falcon` Initial release. Added instrumentation for Falcon 2.0+
- `oxeye_opentelemetry-instrumentation-tornado` Initial release. Supports Tornado 6.x on Python 3.5 and newer.
- `oxeye_opentelemetry-instrumentation-aiohttp-client` Add instrumentor and auto instrumentation support for aiohttp
  ([#1075](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/1075))
- `oxeye_opentelemetry-instrumentation-requests` Add support for instrumenting prepared requests
  ([#1040](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/1040))
- `oxeye_opentelemetry-instrumentation-requests` Add support for http metrics
  ([#1116](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/1116))

### Changed

- `oxeye_opentelemetry-instrumentation-aiohttp-client` Updating span name to match semantic conventions
  ([#972](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/972))
- `oxeye_opentelemetry-instrumentation-dbapi` cursors and connections now produce spans when used with context managers
  ([#1028](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/1028))

### Removed

- Drop support for Python 3.4
  ([#1099](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/1099))

## [0.12b0](https://github.com/ox-eye/oxeye_opentelemetry-python/releases/tag/v0.12.0) - 2020-08-14

### Changed

- `oxeye_opentelemetry-ext-pymemcache` Change package name to oxeye_opentelemetry-instrumentation-pymemcache
  ([#966](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/966))
- `oxeye_opentelemetry-ext-redis` Update default SpanKind to `SpanKind.CLIENT`
  ([#965](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/965))
- `oxeye_opentelemetry-ext-redis` Change package name to oxeye_opentelemetry-instrumentation-redis
  ([#966](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/966))
- `oxeye_opentelemetry-ext-datadog` Change package name to oxeye_opentelemetry-exporter-datadog
  ([#953](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/953))
- `oxeye_opentelemetry-ext-jinja2` Change package name to oxeye_opentelemetry-instrumentation-jinja2
  ([#969](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/969))
- `oxeye_opentelemetry-ext-elasticsearch` Update environment variable names, prefix changed from `oxeye_opentelemetry` to `OTEL`
  ([#904](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/904))
- `oxeye_opentelemetry-ext-elasticsearch` Change package name to oxeye_opentelemetry-instrumentation-elasticsearch
  ([#969](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/969))
- `oxeye_opentelemetry-ext-celery` Change package name to oxeye_opentelemetry-instrumentation-celery
  ([#969](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/969))
- `oxeye_opentelemetry-ext-pyramid` Change package name to oxeye_opentelemetry-instrumentation-pyramid
  ([#966](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/966))
- `oxeye_opentelemetry-ext-pyramid` Update environment variable names, prefix changed from `oxeye_opentelemetry` to `OTEL`
  ([#904](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/904))
- `oxeye_opentelemetry-ext-pymongo` Change package name to oxeye_opentelemetry-instrumentation-pymongo
  ([#966](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/966))
- `oxeye_opentelemetry-ext-sqlite3` Change package name to oxeye_opentelemetry-instrumentation-sqlite3
  ([#966](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/966))
- `oxeye_opentelemetry-ext-sqlalchemy` Change package name to oxeye_opentelemetry-instrumentation-sqlalchemy
  ([#966](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/966))
- `oxeye_opentelemetry-ext-psycopg2` Change package name to oxeye_opentelemetry-instrumentation-psycopg2
  ([#966](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/966))
- `oxeye_opentelemetry-ext-aiohttp-client` Change package name to oxeye_opentelemetry-instrumentation-aiohttp-client
  ([#961](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/961))
- `oxeye_opentelemetry-ext-boto` Change package name to oxeye_opentelemetry-instrumentation-boto
  ([#969](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/969))
- `oxeye_opentelemetry-ext-system-metrics` Change package name to oxeye_opentelemetry-instrumentation-system-metrics
  ([#969](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/969))
- `oxeye_opentelemetry-ext-asgi` Change package name to oxeye_opentelemetry-instrumentation-asgi
  ([#961](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/961))
- `oxeye_opentelemetry-ext-wsgi` Change package name to oxeye_opentelemetry-instrumentation-wsgi
  ([#961](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/961))
- `oxeye_opentelemetry-ext-pymysql` Change package name to oxeye_opentelemetry-instrumentation-pymysql
  ([#966](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/966))
- `oxeye_opentelemetry-ext-requests` Change package name to oxeye_opentelemetry-instrumentation-requests
  ([#961](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/961))
- `oxeye_opentelemetry-ext-requests` Span name reported updated to follow semantic conventions to reduce
  cardinality ([#972](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/972))
- `oxeye_opentelemetry-ext-botocore` Change package name to oxeye_opentelemetry-instrumentation-botocore
  ([#969](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/969))
- `oxeye_opentelemetry-ext-dbapi` Change package name to oxeye_opentelemetry-instrumentation-dbapi
  ([#966](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/966))
- `oxeye_opentelemetry-ext-flask` Change package name to oxeye_opentelemetry-instrumentation-flask
  ([#961](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/961))
- `oxeye_opentelemetry-ext-flask` Update environment variable names, prefix changed from `oxeye_opentelemetry` to `OTEL`
  ([#904](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/904))
- `oxeye_opentelemetry-ext-django` Change package name to oxeye_opentelemetry-instrumentation-django
  ([#961](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/961))
- `oxeye_opentelemetry-ext-django` Update environment variable names, prefix changed from `oxeye_opentelemetry` to `OTEL`
  ([#904](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/904))
- `oxeye_opentelemetry-ext-asyncpg` Change package name to oxeye_opentelemetry-instrumentation-asyncpg
  ([#966](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/966))
- `oxeye_opentelemetry-ext-mysql` Change package name to oxeye_opentelemetry-instrumentation-mysql
  ([#966](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/966))
- `oxeye_opentelemetry-ext-grpc` Change package name to oxeye_opentelemetry-instrumentation-grpc
  ([#969](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/969))

## [0.11b0](https://github.com/ox-eye/oxeye_opentelemetry-python/releases/tag/v0.11.0) - 2020-07-28

### Added

- `oxeye_opentelemetry-instrumentation-aiopg` Initial release
- `oxeye_opentelemetry-instrumentation-fastapi` Initial release
  ([#890](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/890))
- `oxeye_opentelemetry-ext-grpc` Add status code to gRPC client spans
  ([896](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/896))
- `oxeye_opentelemetry-ext-grpc` Add gRPC client and server instrumentors
  ([788](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/788))
- `oxeye_opentelemetry-ext-grpc` Add metric recording (bytes in/out, errors, latency) to gRPC client

### Changed

- `oxeye_opentelemetry-ext-pyramid` Use one general exclude list instead of two
  ([#872](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/872))
- `oxeye_opentelemetry-ext-boto` fails to export spans via jaeger
  ([#866](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/866))
- `oxeye_opentelemetry-ext-botocore` fails to export spans via jaeger
  ([#866](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/866))
- `oxeye_opentelemetry-ext-wsgi` Set span status on wsgi errors
  ([#864](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/864))
- `oxeye_opentelemetry-ext-flask` Use one general exclude list instead of two
  ([#872](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/872))
- `oxeye_opentelemetry-ext-django` Use one general exclude list instead of two
  ([#872](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/872))
- `oxeye_opentelemetry-ext-asyncpg` Shouldn't capture query parameters by default
  ([#854](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/854))
- `oxeye_opentelemetry-ext-mysql` bugfix: Fix auto-instrumentation entry point for mysql
  ([#858](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/858))

## [0.10b0](https://github.com/ox-eye/oxeye_opentelemetry-python/releases/tag/v0.10.0) - 2020-06-23

### Added

- `oxeye_opentelemetry-ext-pymemcache` Initial release
- `oxeye_opentelemetry-ext-elasticsearch` Initial release
- `oxeye_opentelemetry-ext-celery` Add instrumentation for Celery
  ([#780](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/780))
- `oxeye_opentelemetry-instrumentation-starlette` Initial release
  ([#777](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/777))
- `oxeye_opentelemetry-ext-asyncpg` Initial Release
  ([#814](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/814))

## [0.9b0](https://github.com/ox-eye/oxeye_opentelemetry-python/releases/tag/v0.9.0) - 2020-06-10

### Added

- `oxeye_opentelemetry-ext-pyramid` Initial release
- `oxeye_opentelemetry-ext-boto` Initial release
- `oxeye_opentelemetry-ext-botocore` Initial release
- `oxeye_opentelemetry-ext-system-metrics` Initial release
  (https://github.com/ox-eye/oxeye_opentelemetry-python/pull/652)

## [0.8b0](https://github.com/ox-eye/oxeye_opentelemetry-python/releases/tag/v0.8.0) - 2020-05-27

### Added

- `oxeye_opentelemetry-ext-datadog` Add exporter to Datadog
  ([#572](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/572))
- `oxeye_opentelemetry-ext-sqlite3` Initial release
- `oxeye_opentelemetry-ext-psycopg2` Implement instrumentor interface, enabling auto-instrumentation
  ([#694]https://github.com/ox-eye/oxeye_opentelemetry-python/pull/694)
- `oxeye_opentelemetry-ext-asgi` Add ASGI middleware
  ([#716](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/716))
- `oxeye_opentelemetry-ext-django` Add exclude list for paths and hosts to prevent from tracing
  ([#670](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/670))
- `oxeye_opentelemetry-ext-django` Add support for django >= 1.10 (#717)

### Changed

- `oxeye_opentelemetry-ext-grpc` lint: version of grpc causes lint issues
  ([#696](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/696))

## [0.7b1](https://github.com/ox-eye/oxeye_opentelemetry-python/releases/tag/v0.7.1) - 2020-05-12

### Added

- `oxeye_opentelemetry-ext-redis` Initial release
- `oxeye_opentelemetry-ext-jinja2` Add jinja2 instrumentation
  ([#643](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/643))
- `oxeye_opentelemetry-ext-pymongo` Implement instrumentor interface
  ([#612](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/612))
- `oxeye_opentelemetry-ext-sqlalchemy` Initial release
- `oxeye_opentelemetry-ext-aiohttp-client` Initial release
- `oxeye_opentelemetry-ext-pymysql` Initial release
- `oxeye_opentelemetry-ext-http-requests` Implement instrumentor interface, enabling auto-instrumentation
  ([#597](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/597))
- `oxeye_opentelemetry-ext-http-requests` Adding disable_session for more granular instrumentation control
  ([#573](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/573))
- `oxeye_opentelemetry-ext-http-requests` Add a callback for custom attributes
  ([#656](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/656))
- `oxeye_opentelemetry-ext-dbapi` Implement instrument_connection and uninstrument_connection
  ([#624](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/624))
- `oxeye_opentelemetry-ext-flask` Add exclude list for paths and hosts
  ([#630](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/630))
- `oxeye_opentelemetry-ext-django` Initial release
- `oxeye_opentelemetry-ext-mysql` Implement instrumentor interface
  ([#654](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/654))

### Changed

- `oxeye_opentelemetry-ext-http-requests` Rename package to oxeye_opentelemetry-ext-requests
  ([#619](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/619))

## [0.6b0](https://github.com/ox-eye/oxeye_opentelemetry-python/releases/tag/v0.6.0) - 2020-03-30

### Added

- `oxeye_opentelemetry-ext-flask` Add an entry_point to be usable in auto-instrumentation
  ([#327](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/327))
- `oxeye_opentelemetry-ext-grpc` Add gRPC integration
  ([#476](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/476))

## [0.5b0](https://github.com/ox-eye/oxeye_opentelemetry-python/releases/tag/v0.5.0) - 2020-03-16

## [0.4a0](https://github.com/ox-eye/oxeye_opentelemetry-python/releases/tag/v0.4.0) - 2020-02-21

### Added

- `oxeye_opentelemetry-ext-psycopg2` Initial release
- `oxeye_opentelemetry-ext-dbapi` Initial release
- `oxeye_opentelemetry-ext-mysql` Initial release

### Changed

- `oxeye_opentelemetry-ext-pymongo` Updating network connection attribute names
  ([#350](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/350))
- `oxeye_opentelemetry-ext-wsgi` Updating network connection attribute names
  ([#350](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/350))
- `oxeye_opentelemetry-ext-flask` Use string keys for WSGI environ values
  ([#366](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/366))

## [0.3a0](https://github.com/ox-eye/oxeye_opentelemetry-python/releases/tag/v0.3.0) - 2019-12-11

### Added

- `oxeye_opentelemetry-ext-flask` Initial release
- `oxeye_opentelemetry-ext-pymongo` Initial release

### Changed

- `oxeye_opentelemetry-ext-wsgi` Support new semantic conventions
  ([#299](https://github.com/ox-eye/oxeye_opentelemetry-python/pull/299))
- `oxeye_opentelemetry-ext-wsgi` Updates for core library changes

## [0.2a0](https://github.com/ox-eye/oxeye_opentelemetry-python/releases/tag/v0.2.0) - 2019-10-29

### Changed

- `oxeye_opentelemetry-ext-wsgi` Updates for core library changes
- `oxeye_opentelemetry-ext-http-requests` Updates for core library changes

## [0.1a0](https://github.com/ox-eye/oxeye_opentelemetry-python/releases/tag/v0.1.0) - 2019-09-30

### Added

- `oxeye_opentelemetry-ext-wsgi` Initial release
- `oxeye_opentelemetry-ext-http-requests` Initial release
