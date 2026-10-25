Vendored dependencies
=====================

Third-party code copied into ``opentelemetry-instrumentation`` so that it is not
a runtime dependency of the published distribution.

``opentelemetry-instrumentation`` is installed into the target application's
environment by the auto-instrumentation injector, so each of its runtime
dependencies is added to that environment as well and can conflict with a
version the application already pins. Code vendored here is imported under
``opentelemetry.instrumentation._vendor`` and is therefore invisible to the
application and unaffected by whatever versions it installs.

Everything in this directory except ``__init__.py``, ``README.rst`` and
``vendor.txt`` is generated. Do not edit it by hand.

Contents are pinned in ``opentelemetry-instrumentation/vendor.txt`` and produced
by the ``vendoring`` tool, configured under ``[tool.vendoring]`` in
``opentelemetry-instrumentation/pyproject.toml``. From that directory::

    vendoring sync

To move to a newer release of a vendored project::

    vendoring update packaging
    vendoring sync

Review the resulting diff: it is the upstream diff between the two releases,
restricted to the files kept by the ``drop`` list.

Three things need checking on an update. A module added upstream that the
``drop`` list does not name is vendored silently. A ``drop`` entry naming a path
upstream has deleted is skipped without warning. A new absolute import of a
project that is not itself vendored resolves against the application's
environment at runtime rather than against this directory, which would
reintroduce exactly the undeclared dependency this directory exists to avoid.

Two jobs cover this directory. ``.github/workflows/update-vendored-dependencies.yml``
runs weekly, performs the two commands above, and opens a pull request when the
result differs from what is committed. The ``lint-vendoring-check`` tox
environment runs on every pull request and fails if ``vendoring sync`` changes
anything here, which catches both a file edited by hand and a pin bumped without
regenerating.

Both pin the version of the ``vendoring`` tool, because ``sbom.json`` records
the version that generated it.
