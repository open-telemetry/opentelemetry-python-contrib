# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, cast

from opentelemetry._opamp.callbacks import MessageData
from opentelemetry._opamp.client import OpAMPClient
from opentelemetry._opamp.proto import opamp_pb2
from opentelemetry._telemetry_policy import (
    PolicyStore,
    TraceSamplingPolicyImplementer,
    TraceTarget,
)
from opentelemetry._telemetry_policy.opamp import (
    OpAMPPolicyCallbacks,
    OpAMPPolicyProvider,
)

if TYPE_CHECKING:
    from opentelemetry._opamp.agent import OpAMPAgent


def _as_agent(agent: _RecordingAgent) -> OpAMPAgent:
    return cast("OpAMPAgent", agent)


class _RecordingAgent:
    """Stands in for OpAMPAgent; captures status response payloads."""

    def __init__(self) -> None:
        self.sent: list[bytes] = []

    def send(self, payload: bytes) -> None:
        self.sent.append(payload)


def _client() -> OpAMPClient:
    return OpAMPClient(
        endpoint="http://localhost:4320/v1/opamp",
        agent_identifying_attributes={"service.name": "test-service"},
    )


def _policy_document(percentage: float, extra_policies: list[dict[str, Any]] | None = None) -> bytes:
    policies: list[dict[str, Any]] = [
        {
            "id": "sample-database-spans",
            "name": "Sample database spans",
            "trace": {
                "match": [{"span_attribute": ["db.system"], "exists": True}],
                "keep": {"percentage": percentage},
            },
        }
    ]
    policies.extend(extra_policies or [])
    return json.dumps({"policies": policies}).encode("utf-8")


def _remote_config(body: bytes, config_hash: bytes = b"hash-1", key: str = "") -> opamp_pb2.AgentRemoteConfig:
    remote_config = opamp_pb2.AgentRemoteConfig(config_hash=config_hash)
    remote_config.config.config_map[key].body = body
    remote_config.config.config_map[key].content_type = "application/json"
    return remote_config


def _sent_message(agent: _RecordingAgent) -> opamp_pb2.AgentToServer:
    assert len(agent.sent) == 1
    return opamp_pb2.AgentToServer.FromString(agent.sent[0])


def _sent_status(agent: _RecordingAgent) -> opamp_pb2.RemoteConfigStatus:
    return _sent_message(agent).remote_config_status


def _sent_effective_policy_ids(agent: _RecordingAgent, key: str = "") -> list[str]:
    message = _sent_message(agent)
    assert message.HasField("effective_config")
    body = message.effective_config.config_map.config_map[key].body
    return [policy["id"] for policy in json.loads(body)["policies"]]


def _current_percentages(store: PolicyStore) -> list[float]:
    # pylint: disable=protected-access
    return [
        policy.target.keep.percentage
        for policy in store._effective_policies()
        if isinstance(policy.target, TraceTarget)
    ]


def test_remote_config_applied_and_acknowledged() -> None:
    store = PolicyStore()
    store.add_implementer(TraceSamplingPolicyImplementer())
    callbacks = OpAMPPolicyCallbacks(store=store)
    agent = _RecordingAgent()

    callbacks.on_message(_as_agent(agent), _client(), MessageData(remote_config=_remote_config(_policy_document(5.0))))

    assert _current_percentages(store) == [5.0]
    status = _sent_status(agent)
    assert status.status == opamp_pb2.RemoteConfigStatuses_APPLIED
    assert status.last_remote_config_hash == b"hash-1"
    assert status.error_message == ""
    assert _sent_effective_policy_ids(agent) == ["sample-database-spans"]


def test_unchanged_status_not_resent() -> None:
    store = PolicyStore()
    store.add_implementer(TraceSamplingPolicyImplementer())
    callbacks = OpAMPPolicyCallbacks(store=store)
    client = _client()
    agent = _RecordingAgent()

    message = MessageData(remote_config=_remote_config(_policy_document(5.0)))
    callbacks.on_message(_as_agent(agent), client, message)
    callbacks.on_message(_as_agent(agent), client, message)

    assert len(agent.sent) == 1


def test_unparsable_document_reports_failed_and_keeps_policies() -> None:
    store = PolicyStore()
    store.add_implementer(TraceSamplingPolicyImplementer())
    callbacks = OpAMPPolicyCallbacks(store=store)
    client = _client()
    agent = _RecordingAgent()
    callbacks.on_message(_as_agent(agent), client, MessageData(remote_config=_remote_config(_policy_document(5.0))))
    agent.sent.clear()

    callbacks.on_message(
        _as_agent(agent),
        client,
        MessageData(remote_config=_remote_config(b"{ not json", config_hash=b"hash-2")),
    )

    assert _current_percentages(store) == [5.0]
    status = _sent_status(agent)
    assert status.status == opamp_pb2.RemoteConfigStatuses_FAILED
    assert status.last_remote_config_hash == b"hash-2"
    assert "cannot parse policy document" in status.error_message


def test_partially_applied_document_reports_failed_with_details() -> None:
    store = PolicyStore()
    store.add_implementer(TraceSamplingPolicyImplementer())
    callbacks = OpAMPPolicyCallbacks(store=store)
    agent = _RecordingAgent()
    body = _policy_document(5.0, extra_policies=[{"id": "missing-name"}])

    callbacks.on_message(_as_agent(agent), _client(), MessageData(remote_config=_remote_config(body)))

    assert _current_percentages(store) == [5.0]
    status = _sent_status(agent)
    assert status.status == opamp_pb2.RemoteConfigStatuses_FAILED
    assert "missing-name" in status.error_message
    # The reported effective config only contains what actually applied.
    assert _sent_effective_policy_ids(agent) == ["sample-database-spans"]


def test_missing_config_map_key_clears_policies() -> None:
    store = PolicyStore()
    store.add_implementer(TraceSamplingPolicyImplementer())
    callbacks = OpAMPPolicyCallbacks(store=store)
    client = _client()
    agent = _RecordingAgent()
    callbacks.on_message(_as_agent(agent), client, MessageData(remote_config=_remote_config(_policy_document(5.0))))
    agent.sent.clear()

    callbacks.on_message(
        _as_agent(agent),
        client,
        MessageData(remote_config=_remote_config(_policy_document(5.0), config_hash=b"hash-2", key="other")),
    )

    assert _current_percentages(store) == []
    assert _sent_status(agent).status == opamp_pb2.RemoteConfigStatuses_APPLIED
    assert _sent_effective_policy_ids(agent) == []


def test_configured_config_map_key() -> None:
    store = PolicyStore()
    store.add_implementer(TraceSamplingPolicyImplementer())
    callbacks = OpAMPPolicyCallbacks(store=store, config_map_key="vendor")
    agent = _RecordingAgent()

    callbacks.on_message(
        _as_agent(agent),
        _client(),
        MessageData(remote_config=_remote_config(_policy_document(5.0), key="vendor")),
    )

    assert _current_percentages(store) == [5.0]


def test_message_without_remote_config_ignored() -> None:
    store = PolicyStore()
    callbacks = OpAMPPolicyCallbacks(store=store)
    agent = _RecordingAgent()

    callbacks.on_message(_as_agent(agent), _client(), MessageData(remote_config=None))

    assert not agent.sent


def test_provider_construction_and_shutdown() -> None:
    store = PolicyStore()
    provider = OpAMPPolicyProvider(
        endpoint="http://localhost:4320/v1/opamp",
        store=store,
        identifying_attributes={"service.name": "test-service"},
        non_identifying_attributes={"deployment.environment.name": "test"},
    )

    assert provider.source_kind.name == "OPAMP"
    provider.shutdown(timeout=1.0)
