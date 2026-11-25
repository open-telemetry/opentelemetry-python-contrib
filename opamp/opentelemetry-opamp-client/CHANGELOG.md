# Changelog

All notable changes to this project will be documented in this file.

<!--
Do *NOT* add changelog entries here!

This changelog is managed by towncrier and is compiled at release time.

See https://github.com/open-telemetry/opentelemetry-python-contrib/blob/main/CONTRIBUTING.md#changelog for details.
-->

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

<!-- changelog start -->

## Version 0.6b0 (2026-11-11)

### Added

- `opentelemetry-opamp-client`: accept an `AgentToServer` message in
  `OpAMPAgent.send()` and add `OpAMPClient.prepare_message()`
  ([#5107](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/5107))

### Changed

- `opentelemetry-opamp-client`: the `OpAMPClient.build_*_message()` methods
  return an `AgentToServer` message instead of bytes; its instance UID and
  sequence number are set when it is sent
  ([#5107](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/5107))

### Fixed

- `opentelemetry-opamp-client`: adopt the instance UID assigned by the server
  ([#5096](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/5096))
- `opentelemetry-opamp-client`: fix repeated sequence numbers and gaps after
  retries
  ([#5107](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/5107))
- `opentelemetry-opamp-client`: send the instance UID HTTP header matching each
  message
  ([#5285](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/5285))
- Retry the initial state report until a response is received or shutdown
  interrupts it, enabling heartbeats only after a response and preserving
  completion callbacks for failed sends.
  ([#5287](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/5287))

## Version 0.5b0 (2026-10-26)

### Changed

- `opentelemetry-opamp-client`: replaced uuid-utils with a pure Python UUIDv7
  backport from CPython
  ([#5207](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/5207))

## Version 0.4b0 (2026-10-07)

### Added

- `opentelemetry-opamp-client`: allow configuring agent capabilities
  ([#4897](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4897))

### Changed

- `opentelemetry-opamp-client`: bump supported protobuf to < 8
  ([#5151](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/5151))

### Fixed

- Add `requests` to the `opentelemetry-opamp-client` dependencies, fixing a
  `ModuleNotFoundError` when importing `opentelemetry._opamp.client` in a fresh
  environment.
  ([#4930](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4930))

## Version 0.3b0 (2026-07-16)

### Added

- `opentelemetry-opamp-client`: support non-JSON effective config bodies
  ([#4536](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4536))

## Version 0.2b0 (2026-04-01)

- Breaking change: callback class `Callbacks` renamed to `OpAMPCallbacks`
  ([#4355](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4355))

## Version 0.1b0 (2026-03-23)

- Initial implementation
  ([#3635](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3635))
- Update client to have additional callback methods
  ([#4322](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4322))
