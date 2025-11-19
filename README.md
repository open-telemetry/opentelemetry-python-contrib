---
<p align="center">
  <strong>
    <a href="https://opentelemetry.io/docs/instrumentation/python/getting-started/">Getting Started<a/>
    &nbsp;&nbsp;&bull;&nbsp;&nbsp;
    <a href="https://opentelemetry-python-contrib.readthedocs.io/">API Documentation<a/>
    &nbsp;&nbsp;&bull;&nbsp;&nbsp;
    <a href="https://github.com/open-telemetry/opentelemetry-python/discussions">Getting In Touch (GitHub Discussions)<a/>
  </strong>
</p>

<p align="center">
  <a href="https://github.com/open-telemetry/opentelemetry-python-contrib/releases">
    <img alt="GitHub release (latest by date including pre-releases)" src="https://img.shields.io/github/v/release/open-telemetry/opentelemetry-python-contrib?include_prereleases&style=for-the-badge">
  </a>
  <a href="https://codecov.io/gh/open-telemetry/opentelemetry-python-contrib/branch/main/">
    <img alt="Codecov Status" src="https://img.shields.io/codecov/c/github/open-telemetry/opentelemetry-python-contrib?style=for-the-badge">
  </a>
  <a href="https://github.com/open-telemetry/opentelemetry-python-contrib/blob/main/LICENSE">
    <img alt="license" src="https://img.shields.io/badge/license-Apache_2.0-green.svg?style=for-the-badge">
  </a>
  <br/>
  <a href="https://github.com/open-telemetry/opentelemetry-python-contrib/actions/workflows/test_0.yml">
    <img alt="Build Status 0" src="https://github.com/open-telemetry/opentelemetry-python-contrib/actions/workflows/test_0.yml/badge.svg?branch=main">
  </a>
  <a href="https://github.com/open-telemetry/opentelemetry-python-contrib/actions/workflows/test_1.yml">
    <img alt="Build Status 1" src="https://github.com/open-telemetry/opentelemetry-python-contrib/actions/workflows/test_1.yml/badge.svg?branch=main">
  </a>
  <img alt="Beta" src="https://img.shields.io/badge/status-beta-informational?logo=data:image/png;base64,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">
</p>

<p align="center">
  <strong>
    <a href="CONTRIBUTING.md">Contributing<a/>
    &nbsp;&nbsp;&bull;&nbsp;&nbsp;
    <a href="https://opentelemetry-python-contrib.readthedocs.io/en/latest/#instrumentations">Instrumentations<a/>
  </strong>
</p>

---

# OpenTelemetry Python Contrib

The Python auto-instrumentation libraries for [OpenTelemetry](https://opentelemetry.io/) (per [OTEP 0001](https://github.com/open-telemetry/oteps/blob/main/text/0001-telemetry-without-manual-instrumentation.md))

## Index

* [Installation](#installation)
* [Releasing](#releasing)
  * [Releasing a package as `1.0` stable](#releasing-a-package-as-10-stable)
* [Semantic Convention status of instrumentations](#semantic-convention-status-of-instrumentations)
* [Contributing](#contributing)
* [Thanks to all the people who already contributed](#thanks-to-all-the-people-who-already-contributed)

## Installation

This repository includes installable packages for each instrumented library. Libraries that produce telemetry data should only depend on `opentelemetry-api`,
and defer the choice of the SDK to the application developer. Applications may
depend on `opentelemetry-sdk` or another package that implements the API.

**Please note** that these libraries are currently in _beta_, and shouldn't
generally be used in production environments.

Unless explicitly stated otherwise, any instrumentation here for a particular library is not developed or maintained by the authors of such library.

The
[`instrumentation/`](https://github.com/open-telemetry/opentelemetry-python-contrib/tree/main/instrumentation)
directory includes OpenTelemetry instrumentation packages, which can be installed
separately as:

```sh
pip install opentelemetry-instrumentation-{integration}
```

To install the development versions of these packages instead, clone or fork
this repo and do an [editable
install](https://pip.pypa.io/en/stable/topics/local-project-installs/#editable-installs):

```sh
pip install -e ./instrumentation/opentelemetry-instrumentation-{integration}
```

## Releasing

Maintainers release new versions of the packages in `opentelemetry-python-contrib` on a monthly cadence. See [releases](https://github.com/open-telemetry/opentelemetry-python-contrib/releases) for all previous releases.

Contributions that enhance OTel for Python are welcome to be hosted upstream for the benefit of group collaboration. Maintainers will look for things like good documentation, good unit tests, and in general their own confidence when deciding to release a package with the stability guarantees that are implied with a `1.0` release.

To resolve this, members of the community are encouraged to commit to becoming a CODEOWNER for packages in `-contrib` that they feel experienced enough to maintain. CODEOWNERS can then follow the checklist below to release `-contrib` packages as 1.0 stable:

### Releasing a package as `1.0` stable

To release a package as `1.0` stable, the package:

- SHOULD have a CODEOWNER. To become one, submit an issue and explain why you meet the responsibilities found in [CODEOWNERS](.github/CODEOWNERS).
- MUST have unit tests that cover all supported versions of the instrumented library.
  - e.g. Instrumentation packages might use different techniques to instrument different major versions of python packages
- MUST have clear documentation for non-obvious usages of the package
  - e.g. If an instrumentation package uses flags, a token as context, or parameters that are not typical of the `BaseInstrumentor` class, these are documented
- After the release of `1.0`, a CODEOWNER may no longer feel like they have the bandwidth to meet the responsibilities of maintaining the package. That's not a problem at all, life happens! However, if that is the case, we ask that the CODEOWNER please raise an issue indicating that they would like to be removed as a CODEOWNER so that they don't get pinged on future PRs. Ultimately, we hope to use that issue to find a new CODEOWNER.

## Semantic Convention status of instrumentations

In our efforts to maintain optimal user experience and prevent breaking changes for transitioning into stable semantic conventions, OpenTelemetry Python is adopting the semantic convention migration plan for several instrumentations. Currently this plan is only being adopted for [HTTP-related instrumentations](https://github.com/open-telemetry/semantic-conventions/blob/main/docs/non-normative/http-migration.md), but will eventually cover all types. Please refer to the `semconv status` column of the [instrumentation README](instrumentation/README.md) of the current status of instrumentations' semantic conventions. The possible values are `development`, `stable` and `migration` referring to [status](https://github.com/open-telemetry/opentelemetry-specification/blob/v1.31.0/specification/document-status.md#lifecycle-status) of that particular semantic convention. `Migration` refers to an instrumentation that currently supports the migration plan.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md)

We meet weekly on Thursday at 9AM PT. The meeting is subject to change depending on contributors' availability. Check the [OpenTelemetry community calendar](https://calendar.google.com/calendar/embed?src=c_2bf73e3b6b530da4babd444e72b76a6ad893a5c3f43cf40467abc7a9a897f977%40group.calendar.google.com) for specific dates and for the Zoom link.

Meeting notes are available as a public [Google doc](https://docs.google.com/document/d/1CIMGoIOZ-c3-igzbd6_Pnxx1SjAkjwqoYSUWxPY8XIs/edit). For edit access, get in touch on [GitHub Discussions](https://github.com/open-telemetry/opentelemetry-python/discussions).

### Maintainers

- [Aaron Abbott](https://github.com/aabmass), Google
- [Leighton Chen](https://github.com/lzchen), Microsoft
- [Riccardo Magliocchetti](https://github.com/xrmx), Elastic

For more information about the maintainer role, see the [community repository](https://github.com/open-telemetry/community/blob/main/guides/contributor/membership.md#maintainer).

### Approvers

- [Dylan Russell](https://github.com/dylanrussell), Google
- [Emídio Neto](https://github.com/emdneto), PicPay
- [Jeremy Voss](https://github.com/jeremydvoss), Microsoft
- [Liudmila Molkova](https://github.com/lmolkova), Grafana
- [Owais Lone](https://github.com/owais), Splunk
- [Pablo Collins](https://github.com/pmcollins), Splunk
- [Sanket Mehta](https://github.com/sanketmehta28), Cisco
- [Srikanth Chekuri](https://github.com/srikanthccv), signoz.io
- [Tammy Baylis](https://github.com/tammy-baylis-swi), SolarWinds

For more information about the approver role, see the [community repository](https://github.com/open-telemetry/community/blob/main/guides/contributor/membership.md#approver).

### Emeritus Maintainers

- [Alex Boten](https://github.com/codeboten)
- [Diego Hurtado](https://github.com/ocelotl)
- [Owais Lone](https://github.com/owais)
- [Shalev Roda](https://github.com/shalevr)
- [Yusuke Tsutsumi](https://github.com/toumorokoshi)

For more information about the emeritus role, see the [community repository](https://github.com/open-telemetry/community/blob/main/guides/contributor/membership.md#emeritus-maintainerapprovertriager).

### Emeritus Approvers

- [Ashutosh Goel](https://github.com/ashu658)
- [Héctor Hernández](https://github.com/hectorhdzg)
- [Nathaniel Ruiz Nowell](https://github.com/NathanielRN)
- [Nikolay Sokolik](https://github.com/nikosokolik)
- [Nikolay Sokolik](https://github.com/oxeye-nikolay)

For more information about the emeritus role, see the [community repository](https://github.com/open-telemetry/community/blob/main/guides/contributor/membership.md#emeritus-maintainerapprovertriager).

### Thanks to all of our contributors!

<a href="https://github.com/open-telemetry/opentelemetry-python-contrib/graphs/contributors">
  <img alt="Repo contributors" src="https://contrib.rocks/image?repo=open-telemetry/opentelemetry-python-contrib" />
</a>
