# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Added

- Add caching, matching, and targets logic to complete AWS X-Ray Remote Sampler implementation
  ([#3366](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3761))

## Version 2.1.0 (2024-12-24)

- Make ec2 resource detector silent when loaded outside AWS
  ([#3120](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3120))
- Make ecs and beanstalk resource detector silent when loaded outside AWS
  ([#3076](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3076))
- Make EKS resource detector don't warn when not running in EKS
  ([#3074](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3074))

## Version 2.0.2 (2024-08-05)

See [common CHANGELOG](../../CHANGELOG.md) for the changes in this and prior versions.

