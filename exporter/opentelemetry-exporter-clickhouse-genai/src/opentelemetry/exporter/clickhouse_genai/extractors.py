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

"""Extract OpenTelemetry semantic convention attributes into typed columns.

Each extractor function:
1. Pops known attributes from the attrs dict (destructive)
2. Returns a dict with ClickHouse column names as keys
3. Remaining attributes stay in attrs for JSON overflow

Supported semantic convention namespaces:
- db.*: Database operations
- http.*: HTTP client/server operations
- messaging.*: Message queue operations
- rpc.*: RPC operations (gRPC, AWS API)
- net.* / network.* / server.*: Network attributes
- gen_ai.*: GenAI/LLM operations
"""

import json
from typing import Any, Dict


def _to_int(value: Any, default: int = 0) -> int:
    """Safely convert a value to int."""
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _to_str(value: Any, default: str = "") -> str:
    """Safely convert a value to string."""
    if value is None:
        return default
    return str(value)


def extract_db_attributes(attrs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract db.* semantic convention attributes.

    Supports: psycopg, redis, pymongo, sqlalchemy, mysql, sqlite,
    elasticsearch, cassandra, pymemcache
    """
    return {
        "DbSystem": _to_str(attrs.pop("db.system", "")),
        "DbName": _to_str(attrs.pop("db.name", "")),
        "DbStatement": _to_str(attrs.pop("db.statement", "")),
        "DbOperation": _to_str(attrs.pop("db.operation", "")),
        "DbUser": _to_str(attrs.pop("db.user", "")),
        # Redis-specific
        "DbRedisDbIndex": _to_int(attrs.pop("db.redis.database_index", 0)),
        # MongoDB-specific
        "DbMongoCollection": _to_str(attrs.pop("db.mongodb.collection", "")),
    }


def extract_http_attributes(attrs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract http.* semantic convention attributes.

    Supports both old and new semantic conventions:
    - Old: http.method, http.url, http.status_code
    - New: http.request.method, url.full, http.response.status_code
    """
    # Method (try new convention first, fall back to old)
    method = attrs.pop("http.request.method", "") or attrs.pop("http.method", "")

    # URL (try new convention first, fall back to old)
    url = attrs.pop("url.full", "") or attrs.pop("http.url", "")

    # Status code (try new convention first, fall back to old)
    status = attrs.pop("http.response.status_code", 0) or attrs.pop("http.status_code", 0)

    return {
        "HttpMethod": _to_str(method),
        "HttpUrl": _to_str(url),
        "HttpRoute": _to_str(attrs.pop("http.route", "")),
        "HttpTarget": _to_str(attrs.pop("http.target", "") or attrs.pop("url.path", "")),
        "HttpStatusCode": _to_int(status),
        "HttpRequestBodySize": _to_int(
            attrs.pop("http.request.body.size", 0)
            or attrs.pop("http.request_content_length", 0)
        ),
        "HttpResponseBodySize": _to_int(
            attrs.pop("http.response.body.size", 0)
            or attrs.pop("http.response_content_length", 0)
        ),
        "HttpUserAgent": _to_str(
            attrs.pop("user_agent.original", "") or attrs.pop("http.user_agent", "")
        ),
    }


def extract_messaging_attributes(attrs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract messaging.* semantic convention attributes.

    Supports: kafka, rabbitmq, sqs, celery
    """
    return {
        "MessagingSystem": _to_str(attrs.pop("messaging.system", "")),
        "MessagingDestination": _to_str(
            attrs.pop("messaging.destination", "") or attrs.pop("messaging.destination.name", "")
        ),
        "MessagingDestinationKind": _to_str(
            attrs.pop("messaging.destination_kind", "") or attrs.pop("messaging.destination.kind", "")
        ),
        "MessagingOperation": _to_str(attrs.pop("messaging.operation", "")),
        "MessagingMessageId": _to_str(
            attrs.pop("messaging.message_id", "") or attrs.pop("messaging.message.id", "")
        ),
        # Kafka-specific
        "MessagingKafkaPartition": _to_int(attrs.pop("messaging.kafka.partition", -1), -1),
        "MessagingKafkaOffset": _to_int(attrs.pop("messaging.kafka.offset", -1), -1),
        "MessagingKafkaConsumerGroup": _to_str(
            attrs.pop("messaging.kafka.consumer_group", "") or attrs.pop("messaging.kafka.consumer.group", "")
        ),
    }


def extract_rpc_attributes(attrs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract rpc.* and cloud.* semantic convention attributes.

    Supports: gRPC, AWS API (botocore)
    """
    return {
        "RpcSystem": _to_str(attrs.pop("rpc.system", "")),
        "RpcService": _to_str(attrs.pop("rpc.service", "")),
        "RpcMethod": _to_str(attrs.pop("rpc.method", "")),
        "RpcGrpcStatusCode": _to_int(attrs.pop("rpc.grpc.status_code", -1), -1),
        # Cloud/AWS-specific
        "CloudRegion": _to_str(attrs.pop("cloud.region", "")),
        "CloudProvider": _to_str(attrs.pop("cloud.provider", "")),
        "AwsRequestId": _to_str(attrs.pop("aws.request_id", "")),
    }


def extract_network_attributes(attrs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract net.* / network.* / server.* semantic convention attributes.

    Common across all span categories.
    """
    # Peer name (try new convention first, fall back to old)
    peer_name = (
        attrs.pop("network.peer.address", "")
        or attrs.pop("net.peer.name", "")
        or attrs.pop("net.sock.peer.name", "")
    )

    # Peer port (try new convention first, fall back to old)
    peer_port = (
        attrs.pop("network.peer.port", 0)
        or attrs.pop("net.peer.port", 0)
        or attrs.pop("net.sock.peer.port", 0)
    )

    return {
        "NetPeerName": _to_str(peer_name),
        "NetPeerPort": _to_int(peer_port),
        "NetTransport": _to_str(
            attrs.pop("net.transport", "") or attrs.pop("network.transport", "")
        ),
        "ServerAddress": _to_str(attrs.pop("server.address", "")),
        "ServerPort": _to_int(attrs.pop("server.port", 0)),
    }


def extract_genai_attributes(attrs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract gen_ai.* semantic convention attributes for LLM spans.

    Returns attributes for the genai_spans table.
    """
    # Core GenAI attributes
    input_tokens = _to_int(attrs.pop("gen_ai.usage.input_tokens", 0))
    output_tokens = _to_int(attrs.pop("gen_ai.usage.output_tokens", 0))
    total_tokens = _to_int(attrs.pop("llm.usage.total_tokens", 0))

    result = {
        "OperationType": str(attrs.pop("gen_ai.operation.name", "") or ""),
        "Provider": str(attrs.pop("gen_ai.system", "") or ""),
        "RequestModel": str(attrs.pop("gen_ai.request.model", "") or ""),
        "ResponseModel": str(attrs.pop("gen_ai.response.model", "") or ""),
        "ResponseId": str(attrs.pop("gen_ai.response.id", "") or ""),
        # Token usage
        "InputTokens": input_tokens,
        "OutputTokens": output_tokens,
        "TotalTokens": total_tokens,
        # Response info
        "FinishReason": _extract_finish_reason(attrs),
        # Content (if present)
        "RequestContent": str(attrs.pop("gen_ai.request.messages", "") or ""),
        "ResponseContent": str(attrs.pop("gen_ai.response.content", "") or ""),
        "SystemPrompt": str(attrs.pop("gen_ai.prompt", "") or attrs.pop("gen_ai.request.prompt", "") or ""),
    }

    # Calculate total tokens if not provided
    if not result["TotalTokens"] and (result["InputTokens"] or result["OutputTokens"]):
        result["TotalTokens"] = result["InputTokens"] + result["OutputTokens"]

    # Tool calls
    tool_calls = attrs.pop("gen_ai.request.available_tools", [])
    if tool_calls or "tool_calls" in str(result.get("FinishReason", "")):
        result["HasToolCalls"] = 1
        result["ToolCallCount"] = len(tool_calls) if isinstance(tool_calls, list) else 0
    else:
        result["HasToolCalls"] = 0
        result["ToolCallCount"] = 0

    # Extract provider-specific params into JSON
    request_params = {}
    for key in list(attrs.keys()):
        if key.startswith("gen_ai.request."):
            param_name = key.replace("gen_ai.request.", "")
            if param_name not in ("model", "messages", "prompt", "available_tools"):
                request_params[param_name] = attrs.pop(key)

    # Extract response metadata into JSON
    response_meta = {}
    for key in list(attrs.keys()):
        if key.startswith("gen_ai.response.") or key.startswith("gen_ai.openai.response."):
            param_name = key.replace("gen_ai.response.", "").replace(
                "gen_ai.openai.response.", ""
            )
            if param_name not in ("model", "id", "content", "finish_reasons"):
                response_meta[param_name] = attrs.pop(key)

    # Extract token details into JSON
    token_details = {}
    for key in list(attrs.keys()):
        if "tokens" in key.lower() or "token" in key.lower():
            token_details[key] = attrs.pop(key)

    result["RequestParams"] = json.dumps(request_params) if request_params else "{}"
    result["ResponseMeta"] = json.dumps(response_meta) if response_meta else "{}"
    result["TokenDetails"] = json.dumps(token_details) if token_details else "{}"

    return result


def _extract_finish_reason(attrs: Dict[str, Any]) -> str:
    """Extract finish reason from attributes."""
    # Try array format first
    reasons = attrs.pop("gen_ai.response.finish_reasons", [])
    if reasons:
        if isinstance(reasons, (list, tuple)):
            return str(reasons[0]) if reasons else ""
        return str(reasons)

    # Try single value format
    return attrs.pop("gen_ai.response.finish_reason", "")


def extract_error_attributes(attrs: Dict[str, Any]) -> Dict[str, Any]:
    """Extract error-related attributes."""
    error_type = attrs.pop("error.type", "") or attrs.pop("exception.type", "")
    error_message = attrs.pop("exception.message", "") or attrs.pop("error.message", "")

    return {
        "HasError": 1 if error_type else 0,
        "ErrorType": _to_str(error_type),
        "ErrorMessage": _to_str(error_message),
    }


def extract_resource_attributes(resource_attrs: Dict[str, Any]) -> Dict[str, Any]:
    """Extract standard resource attributes."""
    return {
        "ServiceName": _to_str(resource_attrs.pop("service.name", "unknown") or "unknown"),
        "ServiceVersion": _to_str(resource_attrs.pop("service.version", "")),
        "DeploymentEnvironment": _to_str(
            resource_attrs.pop("deployment.environment", "")
            or resource_attrs.pop("deployment.environment.name", "")
        ),
    }


def extract_agent_attributes(attrs: Dict[str, Any]) -> Dict[str, Any]:
    """Extract agent-related attributes (if present)."""
    return {
        "AgentName": _to_str(attrs.pop("agent.name", "") or attrs.pop("gen_ai.agent.name", "")),
        "AgentType": _to_str(attrs.pop("agent.type", "") or attrs.pop("gen_ai.agent.type", "")),
        "AgentStep": _to_int(attrs.pop("agent.step", 0) or attrs.pop("gen_ai.agent.step", 0)),
        "AgentIteration": _to_int(
            attrs.pop("agent.iteration", 0) or attrs.pop("gen_ai.agent.iteration", 0)
        ),
    }


def extract_session_attributes(attrs: Dict[str, Any]) -> Dict[str, Any]:
    """Extract session-related attributes (if present)."""
    return {
        "SessionId": _to_str(
            attrs.pop("session.id", "")
            or attrs.pop("gen_ai.session.id", "")
            or attrs.pop("conversation.id", "")
        ),
        "UserId": _to_str(
            attrs.pop("user.id", "")
            or attrs.pop("gen_ai.user.id", "")
            or attrs.pop("enduser.id", "")
        ),
        "TenantId": _to_str(attrs.pop("tenant.id", "") or attrs.pop("organization.id", "")),
    }
