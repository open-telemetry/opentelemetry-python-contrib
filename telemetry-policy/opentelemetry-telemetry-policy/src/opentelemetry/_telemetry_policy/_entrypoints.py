# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Auto-configuration entry points."""

from __future__ import annotations

import threading
from logging import getLogger
from os import environ
from pathlib import Path

from opentelemetry._telemetry_policy.environment_variables import (
    OTEL_PYTHON_EXPERIMENTAL_OPAMP_ENDPOINT,
    OTEL_PYTHON_EXPERIMENTAL_TELEMETRY_POLICY_FILE,
    OTEL_PYTHON_EXPERIMENTAL_TELEMETRY_POLICY_FILE_POLL_INTERVAL,
    OTEL_PYTHON_EXPERIMENTAL_TELEMETRY_POLICY_OPAMP_KEY,
)
from opentelemetry._telemetry_policy.provider import (
    FilePolicyProvider,
    PolicyProvider,
)
from opentelemetry._telemetry_policy.store import PolicyStore
from opentelemetry._telemetry_policy.trace_sampling import (
    TraceSamplingPolicyImplementer,
)
from opentelemetry.sdk.resources import (
    SERVICE_INSTANCE_ID,
    SERVICE_NAME,
    SERVICE_NAMESPACE,
    Resource,
)
from opentelemetry.sdk.trace.sampling import Sampler, TraceIdRatioBased
from opentelemetry.util.types import AnyValue

_logger = getLogger(__name__)

_IDENTIFYING_ATTRIBUTE_KEYS = (SERVICE_NAME, SERVICE_NAMESPACE, SERVICE_INSTANCE_ID)

_lock = threading.Lock()
# Keep track of providers to be able to reinitialize in tests.
_providers: list[PolicyProvider] = []
_providers_started = False

_store = PolicyStore()

# We don't assume ordering between the sampler factory and post_sdk_init.
# Unless actually started, the trace implementer is very lightweight to initialize,
# so we go ahead and just eagerly initialize it here to avoid ordering constraints.
_trace_implementer = TraceSamplingPolicyImplementer()
_store.add_implementer(_trace_implementer)


def traces_sampler_factory(arg: str | None) -> Sampler:
    """SDK-invoked entrypoint to return the policy sampler."""
    if arg:
        try:
            _trace_implementer.set_fallback(TraceIdRatioBased(float(arg)))
        except ValueError:
            _logger.warning(
                "invalid OTEL_TRACES_SAMPLER_ARG %r for telemetry_policy sampler, using default fallback",
                arg,
            )
    return _trace_implementer.sampler


def post_sdk_init(resource: Resource) -> None:
    """SDK-invoked entrypoint to start configured policy providers if any."""
    policy_file = environ.get(OTEL_PYTHON_EXPERIMENTAL_TELEMETRY_POLICY_FILE)
    opamp_endpoint = environ.get(OTEL_PYTHON_EXPERIMENTAL_OPAMP_ENDPOINT)
    if not policy_file and not opamp_endpoint:
        return

    with _lock:
        global _providers_started  # pylint: disable=global-statement
        if _providers_started:
            _logger.warning(
                "Telemetry policy providers already started. The OpenTelemetry SDK "
                "was initialized more than once in this process"
            )
            return
        _providers_started = True
        store = _store

        if policy_file:
            file_provider = FilePolicyProvider(
                path=Path(policy_file),
                store=store,
                poll_interval=_file_poll_interval(),
            )
            file_provider.start()
            _providers.append(file_provider)

        if opamp_endpoint:
            try:
                from opentelemetry._telemetry_policy.opamp import (  # noqa: PLC0415 # pylint: disable=import-outside-toplevel
                    OpAMPPolicyProvider,
                )
            except ImportError:
                _logger.warning(
                    "%s is set but opentelemetry-opamp-client is not installed. "
                    "Install it with: pip install opentelemetry-telemetry-policy[opamp]",
                    OTEL_PYTHON_EXPERIMENTAL_OPAMP_ENDPOINT,
                )
                return
            opamp_provider = OpAMPPolicyProvider(
                endpoint=opamp_endpoint,
                store=store,
                identifying_attributes=_identifying_attributes(resource),
                non_identifying_attributes=_non_identifying_attributes(resource),
                config_map_key=environ.get(OTEL_PYTHON_EXPERIMENTAL_TELEMETRY_POLICY_OPAMP_KEY, ""),
            )
            opamp_provider.start()
            _providers.append(opamp_provider)


def _file_poll_interval() -> float:
    raw = environ.get(OTEL_PYTHON_EXPERIMENTAL_TELEMETRY_POLICY_FILE_POLL_INTERVAL)
    if raw is None:
        return 30.0
    try:
        return float(raw)
    except ValueError:
        _logger.warning("invalid %s %r, using 30", OTEL_PYTHON_EXPERIMENTAL_TELEMETRY_POLICY_FILE_POLL_INTERVAL, raw)
        return 30.0


def _identifying_attributes(resource: Resource) -> dict[str, AnyValue]:
    return {key: resource.attributes[key] for key in _IDENTIFYING_ATTRIBUTE_KEYS if key in resource.attributes}


def _non_identifying_attributes(resource: Resource) -> dict[str, AnyValue]:
    return {
        key: value
        for key, value in resource.attributes.items()
        if key not in _IDENTIFYING_ATTRIBUTE_KEYS and isinstance(value, (str, bool, int, float))
    }
