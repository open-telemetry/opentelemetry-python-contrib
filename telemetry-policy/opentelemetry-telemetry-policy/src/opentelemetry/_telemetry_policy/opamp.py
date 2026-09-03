# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from collections.abc import Mapping
from logging import getLogger
from typing import Any, cast

from opentelemetry._telemetry_policy.model import SourceKind
from opentelemetry._telemetry_policy.parser import parse_policy_document
from opentelemetry._telemetry_policy.provider import PolicyProvider
from opentelemetry._telemetry_policy.store import PolicyStore
from opentelemetry.util.types import AnyValue

try:
    from opentelemetry._opamp.agent import OpAMPAgent
    from opentelemetry._opamp.callbacks import MessageData, OpAMPCallbacks
    from opentelemetry._opamp.client import OpAMPClient
    from opentelemetry._opamp.proto import opamp_pb2
except ImportError as _import_error:
    raise ImportError(
        "opentelemetry-opamp-client is required for the OpAMP policy provider; "
        "install it with: pip install opentelemetry-telemetry-policy[opamp]"
    ) from _import_error

_logger = getLogger(__name__)


class OpAMPPolicyCallbacks(OpAMPCallbacks):
    """OpAMP callbacks that apply remote config policy documents."""

    def __init__(self, *, store: PolicyStore, config_map_key: str = "") -> None:
        self._store = store
        self._config_map_key = config_map_key

    def on_message(self, agent: OpAMPAgent, client: OpAMPClient, message: MessageData) -> None:
        remote_config = message.remote_config
        if remote_config is None:
            return
        try:
            status, error_message = self._apply_remote_config(client, remote_config)
        except Exception:  # pylint: disable=broad-exception-caught
            _logger.exception("failed to process remote config policies")
            status, error_message = (
                opamp_pb2.RemoteConfigStatuses_FAILED,
                "internal error processing policies",
            )
        updated_status = client.update_remote_config_status(
            remote_config_hash=remote_config.config_hash,
            status=status,
            error_message=error_message,
        )
        if updated_status is not None:
            agent.send(payload=client.build_full_state_message())

    def _apply_remote_config(
        self,
        client: OpAMPClient,
        remote_config: opamp_pb2.AgentRemoteConfig,
    ) -> tuple[opamp_pb2.RemoteConfigStatuses.ValueType, str]:
        config_map = remote_config.config.config_map
        if self._config_map_key not in config_map:
            # Empty policy means explicitly clearing it.
            self._store.set_policies(SourceKind.OPAMP, ())
            self._update_effective_config(client, [])
            return opamp_pb2.RemoteConfigStatuses_APPLIED, ""

        body = config_map[self._config_map_key].body
        try:
            text = body.decode("utf-8")
            result = parse_policy_document(text)
        except (ValueError, UnicodeDecodeError) as exc:
            _logger.warning("cannot parse remote config policy document, keeping previous policies: %s", exc)
            return opamp_pb2.RemoteConfigStatuses_FAILED, f"cannot parse policy document: {exc}"

        errors = [f"policy '{error.policy_id}': {error.message}" for error in result.errors]
        statuses = self._store.set_policies(SourceKind.OPAMP, result.policies)
        errors.extend(f"policy '{status.policy_id}': {status.error}" for status in statuses if not status.applied)

        applied_ids = {status.policy_id for status in statuses if status.applied}
        self._update_effective_config(client, _applied_policies(text, applied_ids))

        if errors:
            return opamp_pb2.RemoteConfigStatuses_FAILED, "; ".join(errors)
        return opamp_pb2.RemoteConfigStatuses_APPLIED, ""

    def _update_effective_config(self, client: OpAMPClient, policies: list[Any]) -> None:
        # FIXME: the policy schema does not specify a payload encoding. JSON
        # is the only encoding parse_policy_document accepts today, but once
        # other encodings are parseable the effective config should be
        # reported in the encoding the remote config arrived in.
        client.update_effective_config({self._config_map_key: {"policies": policies}}, "application/json")


def _applied_policies(text: str, applied_ids: set[str]) -> list[Any]:
    """Filter the received document to the policies that are in effect."""
    document = json.loads(text)
    if isinstance(document, Mapping):
        raw_policies = cast("Mapping[str, Any]", document).get("policies", [document])
    else:
        raw_policies = document
    applied: list[Any] = []
    for raw_policy in cast("list[Any]", raw_policies):
        if isinstance(raw_policy, Mapping) and cast("Mapping[str, Any]", raw_policy).get("id") in applied_ids:
            applied.append(raw_policy)
    return applied


class OpAMPPolicyProvider(PolicyProvider):
    """Receives policy snapshots from an OpAMP server's remote config."""

    def __init__(
        self,
        *,
        endpoint: str,
        store: PolicyStore,
        identifying_attributes: Mapping[str, AnyValue],
        non_identifying_attributes: Mapping[str, AnyValue] | None = None,
        config_map_key: str = "",
        heartbeat_interval: float = 30.0,
        headers: Mapping[str, str] | None = None,
        client: OpAMPClient | None = None,
    ) -> None:
        if client is None:
            client = OpAMPClient(
                endpoint=endpoint,
                headers=headers,
                agent_identifying_attributes=identifying_attributes,
                agent_non_identifying_attributes=non_identifying_attributes,
            )
        self._agent = OpAMPAgent(
            interval=heartbeat_interval,
            callbacks=OpAMPPolicyCallbacks(store=store, config_map_key=config_map_key),
            client=client,
        )

    @property
    def source_kind(self) -> SourceKind:
        return SourceKind.OPAMP

    def start(self) -> None:
        self._agent.start()

    def shutdown(self, timeout: float | None = None) -> None:
        self._agent.stop(timeout)
