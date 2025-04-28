from typing import Dict
from urllib.parse import urlparse

from opentelemetry.semconv._incubating.attributes import (
    server_attributes as ServerAttributes,
)
from opentelemetry.util.types import AttributeValue


def get_server_attributes(endpoint_url: str) -> Dict[str, AttributeValue]:
    """Extract server.* attributes from AWS endpoint URL."""
    parsed = urlparse(endpoint_url)
    attributes = {}
    if parsed.hostname:
        attributes[ServerAttributes.SERVER_ADDRESS] = parsed.hostname
        attributes[ServerAttributes.SERVER_PORT] = parsed.port or 443
    return attributes
