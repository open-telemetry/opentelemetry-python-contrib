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

Fix a finding with a patch, or, once reviewed, add its file (relative to ``destination``) under the
finding's kind in ``[tool.opentelemetry-vendor.allow]`` with a comment explaining why it's safe. An entry
that no longer matches anything is an error, so the list stays current.

Requirements must be pinned with hashes (``--generate-hashes``); ``pip`` then verifies every downloaded
wheel.

If ``sync`` fails, the destination is cleaned back to its protected files, so a half-built tree (unpatched
code, ``*.dist-info`` directories) is never left behind. The ``*.dist-info`` directories are always removed:
their license files and metadata are captured in the copied license files and the SBOM, their ``RECORD`` no
longer matches the rewritten code, and ``importlib.metadata`` can't find them inside a package anyway.

Upgrading vendored packages
---------------------------

1. Edit ``vendor.in``, then re-run the ``uv pip compile ... --generate-hashes`` command recorded at the top
   of the requirements file to update the pins and hashes.
2. Run ``opentelemetry-vendor sync PROJECT_DIR``.
3. If a patch no longer applies, re-create it with the patch workflow above against the new version (or
   remove it if upstream fixed the issue).
4. Review new check findings: patch them, or add the file to ``[tool.opentelemetry-vendor.allow]``. Remove
   allow entries that ``sync`` reports as unused.
5. Review the diff of the vendored files and the SBOM, then run
   ``opentelemetry-vendor sync --check PROJECT_DIR`` to confirm the committed files match ``sync``.
