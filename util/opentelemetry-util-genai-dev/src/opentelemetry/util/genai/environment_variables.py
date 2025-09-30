# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT = (
    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"
)
"""
.. envvar:: OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT

true / false (default: false)
"""

OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT_MODE = (
    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT_MODE"
)
"""
.. envvar:: OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT_MODE
One of ``SPAN_ONLY``, ``EVENT_ONLY``, ``SPAN_AND_EVENT`` (default: ``SPAN_ONLY``).

"""

OTEL_INSTRUMENTATION_GENAI_UPLOAD_HOOK = (
    "OTEL_INSTRUMENTATION_GENAI_UPLOAD_HOOK"
)
"""
.. envvar:: OTEL_INSTRUMENTATION_GENAI_UPLOAD_HOOK
"""

OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH = (
    "OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH"
)
"""
.. envvar:: OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH

An :func:`fsspec.open` compatible URI/path for uploading prompts and responses. Can be a local
path like ``/path/to/prompts`` or a cloud storage URI such as ``gs://my_bucket``. For more
information, see

* `Instantiate a file-system
  <https://filesystem-spec.readthedocs.io/en/latest/usage.html#instantiate-a-file-system>`_ for supported values and how to
  install support for additional backend implementations.
* `Configuration
  <https://filesystem-spec.readthedocs.io/en/latest/features.html#configuration>`_ for
  configuring a backend with environment variables.
*  `URL Chaining
   <https://filesystem-spec.readthedocs.io/en/latest/features.html#url-chaining>`_ for advanced
   use cases.
"""

# ---- Evaluation configuration ----
OTEL_INSTRUMENTATION_GENAI_EVALUATION_ENABLE = (
    "OTEL_INSTRUMENTATION_GENAI_EVALUATION_ENABLE"
)
"""
.. envvar:: OTEL_INSTRUMENTATION_GENAI_EVALUATION_ENABLE

Enable or disable GenAI evaluations. Accepted values (case-insensitive):

* ``true`` / ``1`` / ``yes``: Enable evaluations
* ``false`` / ``0`` / ``no`` (default): Disable evaluations

If disabled, calls to ``TelemetryHandler.evaluate_llm`` will return an empty list without invoking evaluators.
"""

OTEL_INSTRUMENTATION_GENAI_EVALUATORS = "OTEL_INSTRUMENTATION_GENAI_EVALUATORS"
"""
.. envvar:: OTEL_INSTRUMENTATION_GENAI_EVALUATORS

Comma-separated list of evaluator names to run (e.g. ``deepeval,sentiment``). If not provided
and explicit names are not passed to ``evaluate_llm``, no evaluators are run.
"""

OTEL_INSTRUMENTATION_GENAI_EMITTERS = "OTEL_INSTRUMENTATION_GENAI_EMITTERS"
"""
.. envvar:: OTEL_INSTRUMENTATION_GENAI_EMITTERS

Comma-separated list of generators names to run (e.g. ``span,traceloop_compat``).

Select telemetry flavor (composed emitters). Accepted baseline values (case-insensitive):

* ``span`` (default) - spans only
* ``span_metric`` - spans + metrics
* ``span_metric_event`` - spans + metrics + content events

Additional extender emitters:
* ``traceloop_compat`` - adds a Traceloop-compatible LLM span. If specified *alone*, only the compat span is emitted. If combined (e.g. ``span,traceloop_compat``) both semconv and compat spans are produced.

Invalid or unset values fallback to ``span``.
"""

OTEL_INSTRUMENTATION_GENAI_EVALUATION_SPAN_MODE = (
    "OTEL_INSTRUMENTATION_GENAI_EVALUATION_SPAN_MODE"
)
"""
.. envvar:: OTEL_INSTRUMENTATION_GENAI_EVALUATION_SPAN_MODE

Controls evaluation span creation strategy. Accepted values:
* ``off`` (default) - no evaluation spans
* ``aggregated`` - single span summarizing all evaluation metrics
* ``per_metric`` - one span per evaluation metric
"""

# Evaluation async processing interval (seconds, float). Default: 5.0
OTEL_INSTRUMENTATION_GENAI_EVALUATION_INTERVAL = (
    "OTEL_INSTRUMENTATION_GENAI_EVALUATION_INTERVAL"
)
"""
.. envvar:: OTEL_INSTRUMENTATION_GENAI_EVALUATION_INTERVAL

Evaluation async processing interval in seconds (default: 5.0).
"""

# Per-evaluator max sampled invocations per minute (integer). Blank/0 = unlimited.
OTEL_INSTRUMENTATION_GENAI_EVALUATION_MAX_PER_MINUTE = (
    "OTEL_INSTRUMENTATION_GENAI_EVALUATION_MAX_PER_MINUTE"
)
"""
.. envvar:: OTEL_INSTRUMENTATION_GENAI_EVALUATION_MAX_PER_MINUTE

Per-evaluator max sampled invocations per minute. Set to 0 or leave blank for unlimited.
"""

# Backward/defensive: ensure evaluation span mode constant exists even if edits race
try:  # pragma: no cover - defensive
    OTEL_INSTRUMENTATION_GENAI_EVALUATION_SPAN_MODE
except NameError:  # pragma: no cover
    OTEL_INSTRUMENTATION_GENAI_EVALUATION_SPAN_MODE = (
        "OTEL_INSTRUMENTATION_GENAI_EVALUATION_SPAN_MODE"
    )

__all__ = [
    # existing
    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT",
    "OTEL_INSTRUMENTATION_GENAI_UPLOAD_HOOK",
    "OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH",
    # evaluation
    "OTEL_INSTRUMENTATION_GENAI_EVALUATION_ENABLE",
    "OTEL_INSTRUMENTATION_GENAI_EVALUATORS",
    "OTEL_INSTRUMENTATION_GENAI_EVALUATION_SPAN_MODE",
    "OTEL_INSTRUMENTATION_GENAI_EVALUATION_INTERVAL",
    "OTEL_INSTRUMENTATION_GENAI_EVALUATION_MAX_PER_MINUTE",
    # generator selection
    "OTEL_INSTRUMENTATION_GENAI_EMITTERS",
]
