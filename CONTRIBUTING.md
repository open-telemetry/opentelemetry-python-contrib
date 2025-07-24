# Contributing to opentelemetry-python-contrib

The Python special interest group (SIG) meets regularly. See the OpenTelemetry
[community](https://github.com/open-telemetry/community#python-sdk) repo for
information on this and other language SIGs.

See the [public meeting notes](https://docs.google.com/document/d/1CIMGoIOZ-c3-igzbd6_Pnxx1SjAkjwqoYSUWxPY8XIs/edit)
for a summary description of past meetings. To request edit access, join the
meeting or get in touch on [Slack](https://cloud-native.slack.com/archives/C01PD4HUVBL).

See to the [community membership document](https://github.com/open-telemetry/community/blob/main/community-membership.md)
on how to become a [**Member**](https://github.com/open-telemetry/community/blob/main/community-membership.md#member),
[**Approver**](https://github.com/open-telemetry/community/blob/main/community-membership.md#approver)
and [**Maintainer**](https://github.com/open-telemetry/community/blob/main/community-membership.md#maintainer).

Before you can contribute, you will need to sign the [Contributor License Agreement](https://docs.linuxfoundation.org/lfx/easycla/contributors).

Please also read the [OpenTelemetry Contributor Guide](https://github.com/open-telemetry/community/blob/main/guides/contributor/README.md).

## Index

- [Contributing to opentelemetry-python-contrib](#contributing-to-opentelemetry-python-contrib)
  - [Index](#index)
  - [Find a Buddy and get Started Quickly](#find-a-buddy-and-get-started-quickly)
  - [Development](#development)
    - [Virtual Environment](#virtual-environment)
    - [Troubleshooting](#troubleshooting)
    - [Benchmarks](#benchmarks)
  - [Pull Requests](#pull-requests)
    - [How to Send Pull Requests](#how-to-send-pull-requests)
    - [How to Receive Comments](#how-to-receive-comments)
    - [How to Get PRs Reviewed](#how-to-get-prs-reviewed)
    - [How to Get PRs Merged](#how-to-get-prs-merged)
  - [Design Choices](#design-choices)
    - [Focus on Capabilities, Not Structure Compliance](#focus-on-capabilities-not-structure-compliance)
  - [Running Tests Locally](#running-tests-locally)
    - [Testing against a different Core repo branch/commit](#testing-against-a-different-core-repo-branchcommit)
  - [Style Guide](#style-guide)
  - [Guideline for instrumentations](#guideline-for-instrumentations)
    - [Update supported instrumentation package versions](#update-supported-instrumentation-package-versions)
  - [Guideline for GenAI instrumentations](#guideline-for-genai-instrumentations)
    - [Get Involved](#get-involved)
  - [Expectations from contributors](#expectations-from-contributors)
  - [Updating supported Python versions](#updating-supported-python-versions)
    - [Bumping the Python baseline](#bumping-the-python-baseline)
    - [Adding support for a new Python release](#adding-support-for-a-new-python-release)

## Find a Buddy and get Started Quickly

If you are looking for someone to help you find a starting point and be a resource for your first contribution, join our
Slack and find a buddy!

1. Join [Slack](https://slack.cncf.io/) and join our [chat room](https://cloud-native.slack.com/archives/C01PD4HUVBL).
2. Post in the room with an introduction to yourself, what area you are interested in (check issues marked "Help Wanted"),
and say you are looking for a buddy. We will match you with someone who has experience in that area.

Your OpenTelemetry buddy is your resource to talk to directly on all aspects of contributing to OpenTelemetry: providing
context, reviewing PRs, and helping those get merged. Buddies will not be available 24/7, but is committed to responding during their normal contribution hours.

## Development

This project uses [tox](https://tox.readthedocs.io) to automate
some aspects of development, including testing against multiple Python versions.
To install `tox`, run:

```sh
pip install tox
```

You can also run tox with `uv` support. By default [tox.ini](./tox.ini) will automatically create a provisioned tox environment with `tox-uv`, but you can install it at host level:

```sh
pip install tox-uv
```

You can run `tox` with the following arguments:

* `tox` to run all existing tox commands, including unit tests for all packages
  under multiple Python versions
* `tox -e docs` to regenerate all docs
* `tox -e py312-test-instrumentation-aiopg` to e.g. run the aiopg instrumentation unit tests under a specific
  Python version
* `tox -e spellcheck` to run a spellcheck on all the code
* `tox -e lint-some-package` to run lint checks on `some-package`
* `tox -e generate-workflows` to run creation of new CI workflows if tox environments have been updated
* `tox -e ruff` to run ruff linter and formatter checks against the entire codebase

`ruff check` and `ruff format` are executed when `tox -e ruff` is run. We strongly recommend you to configure [pre-commit](https://pre-commit.com/) locally to run `ruff` automatically before each commit by installing it as git hooks. You just need to [install pre-commit](https://pre-commit.com/#install) in your environment:

```console
pip install pre-commit -c dev-requirements.txt
```

and run this command inside the git repository:

```console
pre-commit install
```

See
[`tox.ini`](https://github.com/open-telemetry/opentelemetry-python-contrib/blob/main/tox.ini)
for more detail on available tox commands.

### Virtual Environment

You can also create a single virtual environment to make it easier to run local tests.

For that, you'll need to install [`uv`](https://docs.astral.sh/uv/getting-started/installation/).

After installing `uv`, you can run the following command:

```sh
uv sync
```

This will create a virtual environment in the `.venv` directory and install all the necessary dependencies.

### Troubleshooting

Some packages may require additional system-wide dependencies to be installed. For example, you may need to install `libpq-dev` to run the postgresql client libraries instrumentation tests or `libsnappy-dev` to run the prometheus exporter tests. If you encounter a build error, please check the installation instructions for the package you are trying to run tests for.

For `docs` building, you may need to install `mysql-client` and other required dependencies as necessary. Ensure the Python version used in your local setup matches the version used in the [CI](./.github/workflows/) to maintain compatibility when building the documentation.

### Benchmarks

Some packages have benchmark tests. To run them, run `tox -f benchmark`. Benchmark tests use `pytest-benchmark` and they output a table with results to the console.

To write benchmarks, simply use the [pytest benchmark fixture](https://pytest-benchmark.readthedocs.io/en/latest/usage.html#usage) like the following:

```python
def test_simple_start_span(benchmark):
    def benchmark_start_as_current_span(span_name, attribute_num):
        span = tracer.start_span(
            span_name,
            attributes={"count": attribute_num},
        )
        span.end()

    benchmark(benchmark_start_as_current_span, "benchmarkedSpan", 42)
```

Make sure the test file is under the `benchmarks/` folder of
the package it is benchmarking and further has a path that corresponds to the
file in the package it is testing. Make sure that the file name begins with
`test_benchmark_`. (e.g. `propagator/opentelemetry-propagator-aws-xray/benchmarks/trace/propagation/test_benchmark_aws_xray_propagator.py`)

## Pull Requests

### How to Send Pull Requests

Everyone is welcome to contribute code to `opentelemetry-python-contrib` via GitHub
pull requests (PRs).

To create a new PR, fork the project in GitHub and clone the upstream repo:

```sh
git clone https://github.com/open-telemetry/opentelemetry-python-contrib.git
cd opentelemetry-python-contrib
```

Add your fork as an origin:

```sh
git remote add fork https://github.com/YOUR_GITHUB_USERNAME/opentelemetry-python-contrib.git
```

make sure you have all supported versions of Python installed, install `tox` only for the first time:

```sh
pip install tox tox-uv
```

Run tests in the root of the repository (this will run all tox environments and may take some time):

```sh
tox
```

Check out a new branch, make modifications and push the branch to your fork:

```sh
git checkout -b feature
```

After you edit the files, stage changes in the current directory:

```sh
git add .
```

Then run the following to commit the changes:

```sh
git commit
git push fork feature
```

Open a pull request against the main `opentelemetry-python-contrib` repo.

### How to Receive Comments

* If the PR is not ready for review, please put `[WIP]` in the title, tag it
  as `work-in-progress`, or mark it as [`draft`](https://github.blog/2019-02-14-introducing-draft-pull-requests/).
* Make sure tests and lint are passing locally before requesting a review.
* Make sure CLA is signed and CI is clear.

### How to Get PRs Reviewed

The maintainers and approvers of this repo are not experts in every instrumentation there is here.
In fact each one of us knows enough about them to only review a few. Unfortunately it can be hard
to find enough experts in every instrumentation to quickly review every instrumentation PR. The
instrumentation experts are listed in `.github/component_owners.yml` with their corresponding files
or directories that they own. The owners listed there will be notified when PRs that modify their
files are opened.

If you are not getting reviews, please contact the respective owners directly.

### How to Get PRs Merged

A PR is considered to be **ready to merge** when:

* It has received two approvals from [Approvers](https://github.com/open-telemetry/community/blob/main/community-membership.md#approver)
  / [Maintainers](https://github.com/open-telemetry/community/blob/main/community-membership.md#maintainer)
  (at different companies).
* Major feedbacks are resolved.
* It has been open for review for at least one working day. This gives people
  reasonable time to review.
* Trivial change (typo, cosmetic, doc, etc.) doesn't have to wait for one day.
* Urgent fix can take exception as long as it has been actively communicated.
* A changelog entry is added to the corresponding changelog for the code base, if there is any impact on behavior. e.g. doc entries are not required, but small bug entries are.

Any Approver / Maintainer can merge the PR once it is **ready to merge**.

## Design Choices

As with other OpenTelemetry clients, opentelemetry-python follows the
[opentelemetry-specification](https://github.com/open-telemetry/opentelemetry-specification).

It's especially valuable to read through the [library guidelines](https://github.com/open-telemetry/opentelemetry-specification/blob/main/specification/library-guidelines.md).

### Focus on Capabilities, Not Structure Compliance

OpenTelemetry is an evolving specification, one where the desires and
use cases are clear, but the method to satisfy those uses cases are not.

As such, contributions should provide functionality and behavior that
conforms to the specification, but the interface and structure is flexible.

It is preferable to have contributions follow the idioms of the language
rather than conform to specific API names or argument patterns in the spec.

For a deeper discussion, see: https://github.com/open-telemetry/opentelemetry-specification/issues/165

## Running Tests Locally

1. Go to your Contrib repo directory. `git clone git@github.com:open-telemetry/opentelemetry-python-contrib.git && cd opentelemetry-python-contrib`.
2. Make sure you have `tox` installed. `pip install tox`.
3. Run `tox` without any arguments to run tests for all the packages. Read more about [tox](https://tox.readthedocs.io/en/latest/).

Some tests can be slow due to pre-steps that do dependencies installs. To help with that, you can run tox a first time, and after that run the tests using previous installed dependencies in toxdir as following:

1. First time run (e.g., opentelemetry-instrumentation-aiopg)
```console
tox -e py312-test-instrumentation-aiopg
```
2. Run tests again without pre-steps:
```console
.tox/py312-test-instrumentation-aiopg/bin/pytest instrumentation/opentelemetry-instrumentation-aiopg
```

### Testing against a different Core repo branch/commit

Some of the tox targets install packages from the [OpenTelemetry Python Core Repository](https://github.com/open-telemetry/opentelemetry-python) via pip. The version of the packages installed defaults to the main branch in that repository when tox is run locally. It is possible to install packages tagged with a specific git commit hash by setting an environment variable before running tox as per the following example:

```sh
CORE_REPO_SHA=c49ad57bfe35cfc69bfa863d74058ca9bec55fc3 tox
```

The continuous integration overrides that environment variable with as per the configuration [here](https://github.com/open-telemetry/opentelemetry-python-contrib/blob/main/.github/workflows/test_0.yml#L14).

## Style Guide

* docstrings should adhere to the [Google Python Style
  Guide](http://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings)
  as specified with the [napoleon
  extension](http://www.sphinx-doc.org/en/master/usage/extensions/napoleon.html#google-vs-numpy)
  extension in [Sphinx](http://www.sphinx-doc.org/en/master/index.html).

## Guideline for instrumentations

Below is a checklist of things to be mindful of when implementing a new instrumentation or working on a specific instrumentation. It is one of our goals as a community to keep the implementation specific details of instrumentations as similar across the board as possible for ease of testing and feature parity. It is also good to abstract as much common functionality as possible.

- Follow semantic conventions
  - The instrumentation should follow the semantic conventions defined [here](https://github.com/open-telemetry/semantic-conventions/tree/main/docs).
  - To ensure consistency, we encourage contributions that align with [STABLE](https://opentelemetry.io/docs/specs/otel/document-status/#lifecycle-status) semantic conventions if available. This approach helps us avoid potential confusion and reduces the need to support multiple outdated versions of semantic conventions. However, we are still open to considering exceptional cases where changes are well justified.
  - Contributions related to outdated HTTP semantic conventions (conventions prior to becoming [stable](https://github.com/open-telemetry/semantic-conventions/tree/v1.23.0)) will likely be discouraged, as they increase complexity and the potential for misconceptions.
- Contains a name that is not already claimed in [Pypi](https://pypi.org/). Contact a maintainer, bring the issue up in the weekly Python SIG or create a ticket in Pypi if a desired name has already been taken.
- Extends from [BaseInstrumentor](https://github.com/open-telemetry/opentelemetry-python-contrib/blob/2518a4ac07cb62ad6587dd8f6cbb5f8663a7e179/opentelemetry-instrumentation/src/opentelemetry/instrumentation/instrumentor.py#L35)
- Supports auto-instrumentation
  - Add an entry point (ex. <https://github.com/open-telemetry/opentelemetry-python-contrib/blob/2518a4ac07cb62ad6587dd8f6cbb5f8663a7e179/instrumentation/opentelemetry-instrumentation-requests/pyproject.toml#L44>)
  - Run `python scripts/generate_instrumentation_bootstrap.py` after adding a new instrumentation package.
- Functionality that is common amongst other instrumentation and can be abstracted [here](https://github.com/open-telemetry/opentelemetry-python-contrib/tree/main/opentelemetry-instrumentation/src/opentelemetry/instrumentation)
- Request/response [hooks](https://github.com/open-telemetry/opentelemetry-python-contrib/issues/408) for http instrumentations
- `suppress_instrumentation` functionality
  - ex. <https://github.com/open-telemetry/opentelemetry-python-contrib/blob/2518a4ac07cb62ad6587dd8f6cbb5f8663a7e179/opentelemetry-instrumentation/src/opentelemetry/instrumentation/utils.py#L191>
- Suppress propagation functionality
  - https://github.com/open-telemetry/opentelemetry-python-contrib/issues/344 for more context
- `exclude_urls` functionality
  - ex. <https://github.com/open-telemetry/opentelemetry-python-contrib/blob/2518a4ac07cb62ad6587dd8f6cbb5f8663a7e179/instrumentation/opentelemetry-instrumentation-flask/src/opentelemetry/instrumentation/flask/__init__.py#L327>
- `url_filter` functionality
  - ex. <https://github.com/open-telemetry/opentelemetry-python-contrib/blob/2518a4ac07cb62ad6587dd8f6cbb5f8663a7e179/instrumentation/opentelemetry-instrumentation-aiohttp-client/src/opentelemetry/instrumentation/aiohttp_client/__init__.py#L268>
- `is_recording()` optimization on non-sampled spans
  - ex. <https://github.com/open-telemetry/opentelemetry-python-contrib/blob/2518a4ac07cb62ad6587dd8f6cbb5f8663a7e179/instrumentation/opentelemetry-instrumentation-requests/src/opentelemetry/instrumentation/requests/__init__.py#L234>
- Appropriate error handling
  - ex. <https://github.com/open-telemetry/opentelemetry-python-contrib/blob/2518a4ac07cb62ad6587dd8f6cbb5f8663a7e179/instrumentation/opentelemetry-instrumentation-requests/src/opentelemetry/instrumentation/requests/__init__.py#L220>
- Isolate sync and async test
  - For synchronous tests, the typical test case class is inherited from `opentelemetry.test.test_base.TestBase`. However, if you want to write asynchronous tests, the test case class should inherit also from `IsolatedAsyncioTestCase`. Adding asynchronous tests to a common test class can lead to tests passing without actually running, which can be misleading.
  - ex. <https://github.com/open-telemetry/opentelemetry-python-contrib/blob/60fb936b7e5371b3e5587074906c49fb873cbd76/instrumentation/opentelemetry-instrumentation-grpc/tests/test_aio_server_interceptor.py#L84>
- Most of the instrumentations have the same version. If you are going to develop a new instrumentation it would probably have `X.Y.dev` version and depends on `opentelemetry-instrumentation` and `opentelemetry-semantic-conventions` for a [compatible version](https://peps.python.org/pep-0440/#compatible-release). That means that you may need to install the instrumentation dependencies from this repo and the core repo from git.
- Documentation
  - When adding a new instrumentation remember to add an entry in `docs/instrumentation/` named `<instrumentation>/<instrumentation>.rst` to have the instrumentation documentation referenced from the index. You can use the entry template available [here](./_template/autodoc_entry.rst)
- Testing
  - When adding a new instrumentation remember to update `tox.ini` adding appropriate rules in `envlist`, `command_pre` and `commands` sections

### Update supported instrumentation package versions

- Navigate to the **instrumentation package directory:**
  - Update **`pyproject.toml`** file by modifying `instruments` or `instruments-any` entry in the `[project.optional-dependencies]` section with the new version constraint
  - Update `_instruments` or `_instruments_any` variable in instrumentation **`package.py`** file with the new version constraint
- At the **root of the project directory**, run `tox -e generate` to regenerate necessary files

Please note that `instruments-any` is an optional field that can be used instead of or in addition to `instruments`. While `instruments` is a list of dependencies, _all_ of which are expected by the instrumentation, `instruments-any` is a list _any_ of which but not all are expected. For example, the following entry requires both `util` and `common` plus either `foo` or `bar` to be present for the instrumentation to occur:
```
[project.optional-dependencies]
instruments = [
  "util ~= 1.0"
  "common ~= 2.0"
]
instruments-any = [
  "foo ~= 3.0"
  "bar ~= 4.0"
]
```

<!-- See https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3610 for details on instruments-any -->

If you're adding support for a new version of the instrumentation package, follow these additional steps:

- At the **instrumentation package directory:** Add new test-requirements.txt file with the respective package version required for testing
- At the **root of the project directory**: Add a new test environment entry for the package version in [tox.ini](./tox.ini) and run `tox -e generate-workflows` to regenerate new workflows accordingly. In the same [tox.ini](./tox.ini) file, search for `opentelemetry-instrumentation-{package}/test-requirements` and add a new line to point to the new test-requirements.txt you created in the previous step so tox can install the correct requirements.

Example PRs: [#2976](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2976), [#2845](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2845)

## Guideline for GenAI instrumentations

Instrumentations that relate to [Generative AI](https://opentelemetry.io/docs/specs/semconv/gen-ai/) systems will be placed in the [instrumentation-genai](./instrumentation-genai) folder. This section covers contributions related to those instrumentations. Please note that the [guidelines for instrumentations](#guideline-for-instrumentations) and [expectations from contributors](#expectations-from-contributors) still apply.

### Get Involved

* Reviewing PRs: If you would like to be tagged as reviewer in new PRs related to these instrumentations, please submit a PR to add your GitHub handle to [component_owners.yml](https://github.com/open-telemetry/opentelemetry-python-contrib/blob/main/.github/component_owners.yml) under the corresponding instrumentation folder(s).

* Approving PRs: If you would like to be able to approve PRs related to these instrumentations, you must join [opentelemetry-python-contrib-approvers](https://github.com/orgs/open-telemetry/teams/opentelemetry-python-contrib-approvers) team. Please ask one of the [Python contrib maintainers](https://github.com/orgs/open-telemetry/teams/opentelemetry-python-contrib-maintainers) to be accepted into the team.

* Tracking and Creating Issues: For tracking issues related to Generative AI, please filter or add the label [gen-ai](https://github.com/open-telemetry/opentelemetry-python-contrib/issues?q=is%3Aopen+is%3Aissue+label%3Agen-ai) when creating or searching issues. If you do not see an issue related to an instrumentation you would like to contribute to, please create a new tracking issue so the community is aware of its progress.

## Expectations from contributors

OpenTelemetry is an open source community, and as such, greatly encourages contributions from anyone interested in the project. With that being said, there is a certain level of expectation from contributors even after a pull request is merged, specifically pertaining to instrumentations. The OpenTelemetry Python community expects contributors to maintain a level of support and interest in the instrumentations they contribute. This is to ensure that the instrumentation does not become stale and still functions the way the original contributor intended. Some instrumentations also pertain to libraries that the current members of the community are not so familiar with, so it is necessary to rely on the expertise of the original contributing parties.

## Updating supported Python versions

### Bumping the Python baseline

When updating the minimum supported Python version remember to:

- Remove the version in `pyproject.toml` trove classifiers
- Remove the version from `tox.ini`
- Update github workflows accordingly with `tox -e generate-workflows`
- Search for `sys.version_info` usage and remove code for unsupported versions
- Bump `py-version` in `.pylintrc` for Python version dependent checks

### Adding support for a new Python release

When adding support for a new Python release remember to:

- Add the version in `tox.ini`
- Add the version in `pyproject.toml` trove classifiers
- Update github workflows accordingly with `tox -e generate-workflows`; lint and benchmarks use the latest supported version
- Update `.pre-commit-config.yaml`
- Update tox examples in the documentation
