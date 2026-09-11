# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
OpenTelemetry Python - telemetry policy
---------------------------------------

This package provides an experimental implementation of the telemetry policy concept
proposed in `OTEP 4738`_: policy rules distributed centrally to apply to a running SDK.

Please note that the API is not finalized yet and so the module is called
``_telemetry_policy`` with the underscore.

Usage
-----

With auto-instrumentation, set ``OTEL_TRACES_SAMPLER=telemetry_policy`` to
install the policy sampler and point a provider at a policy source with
``OTEL_PYTHON_EXPERIMENTAL_TELEMETRY_POLICY_FILE`` and/or
``OTEL_PYTHON_EXPERIMENTAL_OPAMP_ENDPOINT``.

Programmatically:

.. code-block:: python

    from opentelemetry import trace
    from opentelemetry._telemetry_policy import (
        FilePolicyProvider,
        PolicyStore,
        TraceSamplingPolicyImplementer,
    )
    from opentelemetry.sdk.trace import TracerProvider

    implementer = TraceSamplingPolicyImplementer()
    tracer_provider = TracerProvider(sampler=implementer.sampler)
    trace.set_tracer_provider(tracer_provider)

    store = PolicyStore()
    store.add_implementer(implementer)
    provider = FilePolicyProvider(path="policies.json", store=store)
    provider.start()

.. _OTEP 4738: https://github.com/open-telemetry/opentelemetry-specification/blob/main/oteps/4738-telemetry-policy.md
"""

from opentelemetry._telemetry_policy.implementer import PolicyImplementer
from opentelemetry._telemetry_policy.model import (
    Contains,
    EndsWith,
    EventAttribute,
    EventNameField,
    Exact,
    Exists,
    LinkTraceIdField,
    LogTarget,
    MatchPredicate,
    MetricTarget,
    Policy,
    PolicyApplyStatus,
    PolicyTarget,
    ProfileTarget,
    Regex,
    ResourceAttribute,
    ScopeAttribute,
    SourceKind,
    SpanAttribute,
    SpanKindField,
    SpanStatusField,
    StartsWith,
    TargetType,
    TraceField,
    TraceMatcher,
    TraceMatcherField,
    TraceSamplingConfig,
    TraceTarget,
)
from opentelemetry._telemetry_policy.provider import (
    FilePolicyProvider,
    PolicyProvider,
)
from opentelemetry._telemetry_policy.store import PolicyStore
from opentelemetry._telemetry_policy.trace_sampling import (
    TraceSamplingPolicyImplementer,
)

__all__ = [
    "Contains",
    "EndsWith",
    "EventAttribute",
    "EventNameField",
    "Exact",
    "Exists",
    "FilePolicyProvider",
    "LinkTraceIdField",
    "LogTarget",
    "MatchPredicate",
    "MetricTarget",
    "Policy",
    "PolicyApplyStatus",
    "PolicyImplementer",
    "PolicyProvider",
    "PolicyStore",
    "PolicyTarget",
    "ProfileTarget",
    "Regex",
    "ResourceAttribute",
    "ScopeAttribute",
    "SourceKind",
    "SpanAttribute",
    "SpanKindField",
    "SpanStatusField",
    "StartsWith",
    "TargetType",
    "TraceField",
    "TraceMatcher",
    "TraceMatcherField",
    "TraceSamplingConfig",
    "TraceSamplingPolicyImplementer",
    "TraceTarget",
]
