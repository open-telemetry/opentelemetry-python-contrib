# Plan for opentelemetry-python-contrib
This document captures the effort to move instrumentation and exporters out of the main repo and into `opentelemetry-python-contrib`. Doing this will give us the ability to decouple changes to the core of OpenTelemetry (API/SDK) from changes to the rest of the eco-system. This pattern is utilized in [other OpenTelemetry SIGs as well](https://github.com/open-telemetry?q=contrib&type=&language=).

## What lives where?
The `opentelemetry-api`, `opentelemetry-sdk` and `opentelemetry-auto-instrumentation` packages will continue to live in the [opentelemetry-python](https://github.com/open-telemetry/opentelemetry-python) repo.

The packages that currently exist in the [ext](https://github.com/open-telemetry/opentelemetry-python/tree/master/ext) folder will be migrated over to the [opentelemetry-python-contrib](https://github.com/open-telemetry/opentelemetry-python-contrib) repository. Currently, packages in that directory are all named `opentelemetry-ext-{package}`, in the contrib repo, these packages will be broken into `opentelemetry-instrumentation-{package}` and `opentelemetry-exporter-{package}`.

## How does code end up in the contrib repo?
There are currently two efforts in progress to bring code to life in the contrib repo.

### Migrating instrumentation/exporter from `opentelemetry-python`
A lot of effort has gone into all the code in the `ext` directory. In order not to lose that work, an effort has been started to migrate over the code to the new contrib repository.

#### Steps to move the instrumentation from opentelemetry-python to opentelemetry-python-contrib repo:
1. copy code to instrumentation directory
2. copy integration tests to instrumentation/opentelemetry-instrumentation-docker-tests directory
3. get a list of the original authors: `git log . | grep Author | sort | uniq`
4. commit the initial move with the list of authors as [`Co-authored by:`](https://help.github.com/en/github/committing-changes-to-your-project/creating-a-commit-with-multiple-authors)
5. add targets to tox

#### Steps to move the exporter from opentelemetry-python to opentelemetry-python-contrib repo:
1. copy code to exporter directory
2. get a list of the original authors: `git log . | grep Author | sort | uniq`
3. commit the initial move with the list of authors as `Co-authored by:`
4. add targets to tox

### Porting instrumentation from the DataDog donation
The original donation from DataDog contains a lot of code that can accelerate the adoption of OpenTelemetry by quickly ramping up the number of supported frameworks and libraries. The steps below describe suggested steps to port integrations from the reference directory containing the originally donated code to OpenTelemetry.

1. Move the code into the instrumentation directory
```
mkdir -p instrumentation/opentelemetry-instrumentation-jinja2/src/opentelemetry/instrumentation/jinja2
git mv reference/ddtrace/contrib/jinja2 instrumentation/opentelemetry-instrumentation-jinja2/src/opentelemetry/instrumentation/jinja2
```
2. Move the tests
```
git mv reference/tests/contrib/jinja2 instrumentation/opentelemetry-instrumentation-jinja2/tests
```
3. Add `README.rst`, `setup.cfg` and `setup.py` files and update them accordingly
```bash
cp _template/* instrumentation/opentelemetry-instrumentation-jinja2/
```
4. Add `version.py` file and update it accordingly
```bash
mv instrumentation/opentelemetry-instrumentation-jinja2/version.py instrumentation/opentelemetry-instrumentation-jinja2/src/opentelemetry/instrumentation/jinja2/version.py
```
5. Fix relative import paths to using ddtrace package instead of using relative paths
6. Update the code and tests to use the OpenTelemetry API

## The contrib repo only has 1 active maintainer, what gives?
Yes this needs to be fixed, folks interested in becoming a maintainer should definitely apply.

## How will changes to contrib packages be released?
The current release process in opentelemetry-python releases all the `ext` packages at the same time as the API and SDK, ideally, changes to individual packages in the contrib repo will be released independently. This will require that this process is as automated as possible as to not become a burden on maintainers.

## How can folks help?
- need to ensure the release process is in place
- help migrate code from opentelemetry-python
- review the open PRs in the opentelemetry-python-contrib

## Where does documentation for the contrib repo live?
Initially the documentation for each package will live in pypi and will provide a link to the opentelemetry docs. Packages in the contrib repo should also be made available in the [opentelemetry registry](https://opentelemetry.io/registry/)

## What order do things need to happen in order to ensure contributors have a good experience?
1. ensure packages committed to contrib can be released
2. create PRs to migrate code into opentelemetry-python-contrib repo and a matching PR to remove the code from the opentelemetry-python repo
3. ensure issues related to instrumentation/exporters are moved to contrib repo
4. ensure we have enough eyes on the repo (approvers/maintainers)

## Will third party exporters be allowed in the contrib repo?
Based on prior commits to the [opentelemetry-collector-contrib](https://github.com/open-telemetry/opentelemetry-collector-contrib) repo, it appears the answer is yes.
