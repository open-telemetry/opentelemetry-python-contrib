
import requests
from mcp.server.fastmcp import FastMCP

def call_http() -> str:
    try:
        response = requests.get("http://www.aws.com", timeout=120)
        return f"HTTP status code: {response.status_code}"
    except Exception as e:
        return f"Error: {str(e)}"

mcp = FastMCP("PythonMcpDemoFoo")

@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b

@mcp.tool()
def subtract(a: int, b: int) -> int:
    """Subtract two numbers"""
    return a - b

@mcp.tool()
def pingweb() -> str:
    """Ping a web URL and return status"""
    return call_http()

# Add a dynamic greeting resource
@mcp.resource("greeting://{name}")
def get_greeting(name: str) -> str:
    """Get a personalized greeting"""
    return f"Hello, {name}!"

def main():
    mcp.run()

if __name__ == "__main__":
     main()