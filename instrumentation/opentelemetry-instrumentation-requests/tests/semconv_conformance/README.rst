Semantic-convention conformance test (requests)
===============================================

This directory checks that this repository's own ``requests`` instrumentation
emits what the OpenTelemetry HTTP semantic conventions require. It runs the same
conformance machinery as the upstream
`semantic-conventions-conformance <https://github.com/open-telemetry/semantic-conventions-conformance>`_
repository, but against the working-tree instrumentation.

It is an ordinary pytest test: it is collected and run by the requests
instrumentation's normal test suite, with no special tox environment and no
special command. Running the requests tests runs this too, and a
semantic-convention violation is a normal test failure.

Client vs server
----------------

``requests`` is an HTTP *client*, so this scenario differs from the Flask one
(which is a server):

- ``conformance.yaml`` declares a ``server:`` that runs the shared mock HTTP
  server (``http-mock-server``). The runner starts it, chooses its port, and
  publishes its base URL to the scenario as ``MOCK_SERVER_URL``.
- ``client.py`` is the shared client workload: it drives the contract's request
  sequence at that mock server, using this library's own ``requests.Session``.
  It turns on no instrumentation.
- ``scenario.py`` turns on exactly one instrumentation
  (``RequestsInstrumentor``) and runs the workload. The instrumentation it
  imports is this repository's own working-tree package.
- There is no ``otel-http-drive --serve`` wrapper here (that is for a server
  scenario, where the driver sends requests at the framework under test from
  outside its process). A client scenario is itself the sender.

Everything else is the same as the Flask conformance test.

Shared harness
--------------

``conftest.py`` is the shared conformance harness: it puts the pinned Weaver
binary on ``PATH`` (downloading and caching it if needed) and fetches the pinned
semantic-conventions registry on demand, and skips the conformance test with a
clear reason if either cannot be obtained (for example offline). It is
byte-for-byte identical to the ``conftest.py`` under every other
instrumentation's ``tests/semconv_conformance/``. When changing it, copy the
change to the others.

The conformance tooling is not on PyPI, so it is installed from a pinned commit
of the conformance repository, listed in this package's ``test-requirements.txt``
alongside the other test dependencies (``pytest`` is bumped to ``>=8`` because
the tooling requires it).

Running it
----------

Just run the requests tests. Locally::

    tox -e py312-test-instrumentation-requests

or plain ``pytest`` inside an environment that installed
``test-requirements.txt``::

    pytest instrumentation/opentelemetry-instrumentation-requests/tests/semconv_conformance

In CI it runs automatically as part of the generated ``test.yml`` matrix for the
requests environment; no separate workflow.

Adding the next instrumentation
-------------------------------

Copy this directory's ``conftest.py`` unchanged, add a ``scenario.py`` +
``conformance.yaml`` (server-shaped like Flask or client-shaped like this one),
add the four pinned conformance-tooling requirements and ``pytest>=8`` to that
instrumentation's existing ``test-requirements``. No new tox environment and no
new CI workflow are needed. Keep the pinned conformance-repo commit identical
across every instrumentation, and keep the Weaver version in ``conftest.py`` in
sync with that pin.
