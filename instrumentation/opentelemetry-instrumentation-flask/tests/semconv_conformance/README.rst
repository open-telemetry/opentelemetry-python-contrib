Semantic-convention conformance test (Flask)
============================================

This directory checks that this repository's own Flask instrumentation emits
what the OpenTelemetry HTTP semantic conventions require. It runs the same
conformance machinery as the upstream
`semantic-conventions-conformance <https://github.com/open-telemetry/semantic-conventions-conformance>`_
repository, but against the working-tree instrumentation.

It is an ordinary pytest test: it is collected and run by the Flask
instrumentation's normal test suite, with no special tox environment and no
special command. Running the Flask tests runs this too, and a
semantic-convention violation is a normal test failure.

How it works
------------

- ``server.py`` is the shared HTTP server workload: a Flask app declaring the
  contract's routes with Flask's own decorators, and nothing else. It is copied
  from the upstream conformance repo so this instrumentation is measured against
  the same request contract every language and framework is.
- ``scenario.py`` turns on exactly one instrumentation (``FlaskInstrumentor``)
  and serves that app. The instrumentation it imports is this repository's own
  working-tree package, installed editable by the normal flask test env.
- ``conformance.yaml`` declares the run: ``runner: http-conformance``, the
  instrumented and instrumentation library names, the
  ``OTEL_SEMCONV_STABILITY_OPT_IN=http`` opt-in, and the command that runs the
  scenario. The ``opentelemetry-conformance`` pytest plugin (registered through
  its ``pytest11`` entry point when the tooling is installed) collects this
  ``conformance.yaml`` during normal collection and runs each declared scenario
  as a pytest test.
- ``conftest.py`` makes the test self-contained: on the first collection it puts
  the pinned Weaver binary on ``PATH`` (downloading and caching it if needed)
  and fetches the pinned semantic-conventions registry into the tooling's cache.
  If either cannot be obtained (for example offline), it skips the conformance
  test with a clear reason rather than erroring. Nothing has to be
  pre-provisioned by hand.

The conformance tooling is not on PyPI, so it is installed from a pinned commit
of the conformance repository, listed in this package's ``test-requirements-3.txt``
alongside the other test dependencies (that env's ``pytest`` is bumped to ``>=8``
because the tooling requires it; the older flask envs keep their pin and simply
do not collect this test).

Running it
----------

Just run the flask tests. Locally::

    tox -e py312-test-instrumentation-flask-3

or plain ``pytest`` inside an environment that installed
``test-requirements-3.txt``::

    pytest instrumentation/opentelemetry-instrumentation-flask/tests/semconv_conformance

In CI it runs automatically as part of the generated ``test.yml`` matrix for the
flask-3 environment; no separate workflow.

Adding the next instrumentation
-------------------------------

This harness is meant to be reused, with the same "normal pytest test" shape. To
add, for example, ``requests`` (a client instrumentation):

1. Create ``instrumentation/opentelemetry-instrumentation-requests/tests/semconv_conformance/``
   with a ``scenario.py`` that turns on ``RequestsInstrumentor`` and drives the
   shared client workload, a ``conformance.yaml`` with
   ``instrumented_library: requests``,
   ``instrumentation_library: opentelemetry-instrumentation-requests``, a
   ``server:`` line running ``http-mock-server --port ${PORT}``, and a
   ``client`` scenario. Use the Flask files here and the upstream conformance
   repo's ``requests`` scenario as the templates. A server framework reuses the
   Flask ``server.py``/``scenario.py`` shape instead.
2. Copy this directory's ``conftest.py`` into that new directory unchanged (it is
   generic: it provisions Weaver and the registry for whatever
   ``conformance.yaml`` is collected beneath it).
3. Add the four pinned conformance-tooling requirements (identical to the block
   in this package's ``test-requirements-3.txt``) to one of that instrumentation's
   normal ``test-requirements*.txt`` files, and bump that file's ``pytest`` to
   ``>=8``. No new tox environment and no new CI workflow are needed: it runs in
   that instrumentation's existing test env and the normal ``test.yml`` matrix.

Keep the pinned conformance-repo commit identical across every instrumentation's
requirements so they are all checked by the same tooling version, and keep the
Weaver version in ``conftest.py`` in sync with that pin.
