#!/usr/bin/env python3
"""MCP server with HTTP transport using SSE."""

import boto3  # type: ignore[import-untyped]
import requests
from mcp.server.fastmcp import FastMCP


def call_http(url: str) -> str:
    try:
        response = requests.get(url, timeout=5)
        return f"HTTP call succeeded. Status: {response.status_code}, Body length: {len(response.content)} bytes"
    except requests.RequestException as exc:
        return f"HTTP call failed: {str(exc)}"


def call_s3() -> str:
    try:
        s3_client = boto3.client("s3")  # type: ignore[no-untyped-call]
        response = s3_client.list_buckets()  # type: ignore[no-untyped-call]
        bucket_list = response.get("Buckets", [])  # type: ignore[union-attr]
        buckets = ", ".join(
            [str(bucket.get("Name", "")) for bucket in bucket_list]  # type: ignore[union-attr]
        )
        if not buckets:
            buckets = "No buckets found"
        return f"S3 call succeeded. Buckets: {buckets}"
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return f"S3 call failed: {str(exc)}"


mcp = FastMCP("MCP HTTP Server")


@mcp.tool()  # type: ignore[misc]
def add(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b


@mcp.tool()  # type: ignore[misc]
def multiply(a: int, b: int) -> int:
    """Multiply two numbers"""
    return a * b


@mcp.tool()  # type: ignore[misc]
def pingweb(url: str) -> str:
    """Make an HTTP GET request to the specified URL"""
    return call_http(url)


@mcp.tool()  # type: ignore[misc]
def awssdkcall() -> str:
    """Make an AWS S3 API call to list buckets"""
    return call_s3()


@mcp.resource("greeting://{name}")  # type: ignore[misc]
def get_greeting(name: str) -> str:
    """Get a personalized greeting"""
    return f"Hello, {name}!"


if __name__ == "__main__":
    # Run with SSE transport on port 8000
    mcp.run(transport="sse")
