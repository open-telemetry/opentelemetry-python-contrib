HTTP semantic convention stability opt-in
-----------------------------------------

HTTP instrumentations emit the old experimental HTTP semantic conventions by
default. To emit only the stable HTTP and networking semantic conventions, set
``OTEL_SEMCONV_STABILITY_OPT_IN=http`` before starting the instrumented
process.

To emit both the old and stable HTTP semantic conventions during migration, set
``OTEL_SEMCONV_STABILITY_OPT_IN=http/dup``. The value can be combined with
other signal opt-ins as a comma-separated list.

For example:

.. code-block:: sh

    export OTEL_SEMCONV_STABILITY_OPT_IN=http
