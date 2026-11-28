OpenTelemetry Vendor
====================

Patches
-------

Vendored packages can be modified with patch files listed, in order, under the ``patches`` key of
``[tool.opentelemetry-vendor]`` (paths relative to the project directory). ``sync`` applies them with
``git apply`` after imports have been rewritten, so they are written against the rewritten code and the paths
inside them are relative to ``destination``. All patches are applied, or none are.

Text above the first ``diff --git`` line is ignored by ``git apply``; use it to explain why the patch exists.
Each patch is recorded in the SBOM as the pedigree of the package it modifies.

To write a patch:

1. Run ``opentelemetry-vendor sync PROJECT_DIR`` and commit (or stage) the vendored files.
2. Edit the vendored files.
3. Run ``git diff --relative=<destination> > patches/<name>.patch`` from the project directory and add an
   explanation at the top.
4. Add the patch to ``patches`` and run ``sync`` again to check that it applies.

Checks
------

After rewriting and patching, ``sync`` checks the vendored code for anything that escapes the vendor
namespace and fails on findings that haven't been reviewed:

* ``imports``: an absolute import of a vendored package (e.g. added by a patch). Always an error.
* ``dynamic-imports``: ``__import__``, ``importlib.import_module``, ``importlib.resources`` lookups and
  ``sys.modules`` writes that can load modules by their top-level names.
* ``logger-names``: ``logging.getLogger("<vendored name>")`` calls left after rewriting.
* ``module-names``: vendored module names left in protobuf builder calls of generated ``*_pb2`` code
  (``BuildTopDescriptorsAndMessages(DESCRIPTOR, "<module>", ...)``), which set the classes' ``__module__``.
* ``side-effects``: changes to process-global state: warning filters and environment variables.
* ``external-imports``: absolute imports of modules that are neither vendored nor in the standard library,
  which load the application's copy. Expected where vendored code patches the application's libraries
  (instrumentations), or for optional, guarded integrations.

Fix a finding with a patch, or, once reviewed, add its file (relative to ``destination``) under the
finding's kind in ``[tool.opentelemetry-vendor.allow]`` with a comment explaining why it's safe. Entries are
``fnmatch`` patterns (``*`` also matches ``/``), e.g. ``opentelemetry/instrumentation/*``. An entry that no
longer matches anything is an error, so the list stays current.

Requirements must be pinned with hashes (``--generate-hashes``); ``pip`` then verifies every downloaded
wheel.

If ``sync`` fails, the destination is cleaned back to its protected files, so a half-built tree (unpatched
code, ``*.dist-info`` directories) is never left behind. The ``*.dist-info`` directories are always removed:
their license files and metadata are captured in the copied license files and the SBOM, their ``RECORD`` no
longer matches the rewritten code, and ``importlib.metadata`` can't find them inside a package anyway.

Entry points
------------

The ``*.dist-info`` directories are removed, but vendored code can discover plugins through
``importlib.metadata`` entry points (OpenTelemetry does). With ``metadata-dir`` (relative to
``destination``), ``sync`` keeps each vendored distribution's ``METADATA`` and ``entry_points.txt`` in
``<metadata-dir>/<name>-<version>.dist-info/``, with entry point modules moved under the vendor namespace
and the ``console_scripts``/``gui_scripts`` groups dropped. An entry point whose module isn't in the vendored
tree (dropped, or its distribution excluded) is an error. The directory isn't on ``sys.path``: vendored code
finds it only through an explicit ``importlib.metadata.distributions(path=[...])``, set up by a patch.

License files
-------------

Every vendored wheel must ship a license file. For a wheel that doesn't, map its distribution to a license
file of the project under ``[tool.opentelemetry-vendor.license-files]``; the entry becomes an error once the
wheel ships its own.

Native extensions
-----------------

``sync`` vendors pure-Python wheels only; that tree is committed and makes the pure (``py3-none-any``) agent
wheel. For platform wheels, ``opentelemetry-vendor build-native PROJECT_DIR`` builds the native extensions of
the distributions configured under ``[tool.opentelemetry-vendor.native.<distribution>]`` into the vendor tree:

1. It downloads the distribution's hash-pinned sdist (from the requirements file) and extracts it.
2. It applies the entry's ``patches`` (paths inside are relative to the sdist root). They must move the
   extension, and every module name compiled into it (its own and those it imports by absolute name), under
   the vendor namespace, and build it with the stable ABI (``abi3``).
3. It builds a wheel with PEP 517 in a temporary virtual environment holding the hash-pinned
   ``build-requirements``, and copies the namespaced ``abi3`` extensions into the vendor tree.
4. It checks the binaries for un-namespaced vendored module names (``native-module-names``; reviewed
   exceptions go in ``[tool.opentelemetry-vendor.allow]``) and records the native build in the SBOM.

It must run on CPython at ``python-version`` (abi3 extensions are compiled against the oldest supported
Python) and refuses free-threaded interpreters, which use the pure wheel. Then build the wheel from the
source tree (not from the sdist, which doesn't contain the compiled extensions); the agent's build hook tags
it ``cp310-abi3-<platform>``. ``opentelemetry-vendor build-native --clean PROJECT_DIR`` removes the extensions
and restores the committed SBOM. A failed build cleans up after itself.

Upgrading vendored packages
---------------------------

1. Edit ``vendor.in``, then re-run the ``uv pip compile ... --generate-hashes`` command recorded at the top
   of the requirements file to update the pins and hashes. Dependencies that must not be vendored (e.g.
   without a pure-Python wheel) are left out of the resolution with ``--excludes <file>``; ``sync`` downloads
   exactly the pinned wheels (``pip download --no-deps``).
2. Run ``opentelemetry-vendor sync PROJECT_DIR``.
3. If a patch no longer applies, re-create it with the patch workflow above against the new version (or
   remove it if upstream fixed the issue).
4. Review new check findings: patch them, or add the file to ``[tool.opentelemetry-vendor.allow]``. Remove
   allow entries that ``sync`` reports as unused.
5. Review the diff of the vendored files and the SBOM, then run
   ``opentelemetry-vendor sync --check PROJECT_DIR`` to confirm the committed files match ``sync``.
