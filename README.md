# opentelemetry-auto-instr-python
The auto-instrumentation for Python (per [OTEP 0001](https://github.com/open-telemetry/oteps/blob/master/text/0001-telemetry-without-manual-instrumentation.md)) instruments each library in a separately installable package to ensure users only need to install the libraries that make sense for their use-case. This repository contains the code initially [donate by DataDog](https://www.datadoghq.com/blog/opentelemetry-instrumentation/) in the `reference` folder. All instrumentation that has been ported lives in the `instrumentors` directory.

# porting ddtrace/contrib to instrumentors

The steps below describe the process to port integrations from the reference directory containing the originally donated code to OpenTelemetry.

1. Move the code into the instrumentors directory

```
git mv reference/ddtrace/contrib/jinja2 instrumentors/
```

2. Move the tests

```
git mv reference/tests/contrib/jinja2 instrumentors/jinja2/tests
```

3. Make the package installable: move source code to package path

```bash
mkdir -p instrumentors/jinja2/src/opentelemetry/ext/jinja2
git mv instrumentors/jinja2/*.py instrumentors/jinja2/src/opentelemetry/ext/jinja2
```

4. Add `README.rst`, `setup.cfg` and `setup.py` files and update them accordingly

```bash
cp _template/* instrumentors/jinja2/
```

5. Add `version.py` file and update it accordingly

```bash
mv instrumentors/jinja2/version.py instrumentors/jinja2/src/opentelemetry/ext/jinja2/version.py
```

6. Fix relative import paths to using ddtrace package instead of using relative paths
7. Update the code and tests to use the OpenTelemetry API
