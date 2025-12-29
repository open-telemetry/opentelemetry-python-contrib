"""
OpenTelemetry Tracing Demo with Weaviate and OpenAI

This example demonstrates how OpenTelemetry auto-instrumentation traces:
- Flask HTTP requests (creates root span for unified traces)
- Weaviate vector database operations
- OpenAI API calls (embeddings and chat completions)
- HTTP requests (httpx, requests, urllib3)

The application uses Flask to provide a unified trace context:
1. GET /demo - Runs the full demo and returns results
2. All operations are automatically traced under the Flask request span

All operations are automatically traced and can be viewed in Jaeger.
This is a ZERO-CODE instrumentation example - no OpenTelemetry imports needed!
"""

import os
import time

import httpx
import requests
import weaviate
from flask import Flask, jsonify
from openai import OpenAI

app = Flask(__name__)


def get_weaviate_client():
    """Connect to Weaviate instance."""
    weaviate_url = os.getenv("WEAVIATE_URL", "http://localhost:8080")
    print(f"Connecting to Weaviate at {weaviate_url}...")

    # Parse the URL to get host and port
    url_parts = weaviate_url.replace("http://", "").replace("https://", "").split(":")
    host = url_parts[0]
    port = int(url_parts[1]) if len(url_parts) > 1 else 8080

    client = weaviate.connect_to_custom(
        http_host=host,
        http_port=port,
        http_secure=False,
        grpc_host=host,
        grpc_port=50051,
        grpc_secure=False,
    )
    print("Connected to Weaviate!")
    return client


def get_openai_client():
    """Get OpenAI client."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is required")
    return OpenAI(api_key=api_key)


def create_collection(weaviate_client, collection_name: str):
    """Create a Weaviate collection for storing articles."""
    print(f"\nCreating collection '{collection_name}'...")

    # Delete if exists
    if weaviate_client.collections.exists(collection_name):
        print(f"Collection '{collection_name}' already exists, deleting...")
        weaviate_client.collections.delete(collection_name)

    # Create the collection
    collection = weaviate_client.collections.create(
        name=collection_name,
        properties=[
            weaviate.classes.config.Property(
                name="title",
                data_type=weaviate.classes.config.DataType.TEXT,
            ),
            weaviate.classes.config.Property(
                name="content",
                data_type=weaviate.classes.config.DataType.TEXT,
            ),
            weaviate.classes.config.Property(
                name="category",
                data_type=weaviate.classes.config.DataType.TEXT,
            ),
        ],
    )
    print(f"Collection '{collection_name}' created successfully!")
    return collection


def generate_embedding(openai_client, text: str) -> list:
    """Generate embedding for text using OpenAI."""
    response = openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=text,
    )
    return response.data[0].embedding


def insert_articles(weaviate_client, openai_client, collection_name: str):
    """Insert sample articles with embeddings."""
    print("\nGenerating embeddings and inserting articles...")

    articles = [
        {
            "title": "Introduction to Machine Learning",
            "content": "Machine learning is a subset of artificial intelligence that enables systems to learn and improve from experience without being explicitly programmed.",
            "category": "Technology",
        },
        {
            "title": "The Future of Renewable Energy",
            "content": "Solar and wind power are becoming increasingly cost-effective, making renewable energy a viable alternative to fossil fuels for many applications.",
            "category": "Environment",
        },
        {
            "title": "Deep Learning Fundamentals",
            "content": "Deep learning uses neural networks with multiple layers to progressively extract higher-level features from raw input data.",
            "category": "Technology",
        },
        {
            "title": "Climate Change and Its Effects",
            "content": "Global warming is causing significant changes to weather patterns, sea levels, and ecosystems around the world.",
            "category": "Environment",
        },
        {
            "title": "Natural Language Processing Advances",
            "content": "NLP has made significant strides with transformer models, enabling more natural interactions between humans and machines.",
            "category": "Technology",
        },
    ]

    collection = weaviate_client.collections.get(collection_name)

    for i, article in enumerate(articles):
        print(f"  Processing article {i + 1}/{len(articles)}: {article['title']}")

        # Generate embedding for the content
        text_for_embedding = f"{article['title']} {article['content']}"
        embedding = generate_embedding(openai_client, text_for_embedding)

        # Insert into Weaviate with vector
        collection.data.insert(
            properties={
                "title": article["title"],
                "content": article["content"],
                "category": article["category"],
            },
            vector=embedding,
        )

    print(f"Inserted {len(articles)} articles successfully!")


def query_similar_articles(weaviate_client, openai_client, collection_name: str, query: str):
    """Query Weaviate for similar articles."""
    print(f"\nSearching for articles similar to: '{query}'")

    # Generate embedding for the query
    query_embedding = generate_embedding(openai_client, query)

    collection = weaviate_client.collections.get(collection_name)

    # Query Weaviate using vector search
    results = collection.query.near_vector(
        near_vector=query_embedding,
        limit=3,
        return_metadata=weaviate.classes.query.MetadataQuery(distance=True),
        return_properties=["title", "content", "category"],
    )

    print(f"Found {len(results.objects)} similar articles:")
    articles = []
    for obj in results.objects:
        distance = obj.metadata.distance if obj.metadata.distance is not None else 0
        print(f"  - {obj.properties['title']} (distance: {distance:.4f})")
        articles.append(obj.properties)

    return articles


def summarize_with_openai(openai_client, articles: list, query: str):
    """Use OpenAI to summarize the search results."""
    print("\nGenerating summary with OpenAI...")

    articles_text = "\n\n".join([
        f"Title: {a['title']}\nContent: {a['content']}\nCategory: {a['category']}"
        for a in articles
    ])

    response = openai_client.chat.completions.create(
        model="gpt-5-nano",
        messages=[
            {
                "role": "system",
                "content": "You are a helpful assistant that summarizes search results. Be concise and informative.",
            },
            {
                "role": "user",
                "content": f"Based on the following search query: '{query}'\n\nHere are the relevant articles:\n\n{articles_text}\n\nPlease provide a brief summary of how these articles relate to the query.",
            },
        ]
    )

    summary = response.choices[0].message.content
    print(f"\nSummary:\n{summary}")
    return summary


def make_sample_http_requests():
    """Make sample HTTP requests to demonstrate HTTP tracing."""
    print("\nMaking sample HTTP requests to demonstrate tracing...")

    # Using requests library
    print("  - Making request with 'requests' library...")
    try:
        resp = requests.get("https://httpbin.org/get", timeout=10)
        print(f"    Status: {resp.status_code}")
    except Exception as e:
        print(f"    Error: {e}")

    # Using httpx library (sync)
    print("  - Making request with 'httpx' library...")
    try:
        with httpx.Client() as client:
            resp = client.get("https://httpbin.org/headers", timeout=10)
            print(f"    Status: {resp.status_code}")
    except Exception as e:
        print(f"    Error: {e}")

    print("  HTTP requests completed!")


def run_demo():
    """Run the full demo workflow."""
    collection_name = "Articles"

    # Initialize clients
    weaviate_client = get_weaviate_client()
    openai_client = get_openai_client()

    results = {
        "status": "success",
        "steps": []
    }

    try:
        # Make sample HTTP requests first
        make_sample_http_requests()
        results["steps"].append("HTTP requests completed")

        # Create collection
        create_collection(weaviate_client, collection_name)
        results["steps"].append(f"Collection '{collection_name}' created")

        # Insert articles with embeddings
        insert_articles(weaviate_client, openai_client, collection_name)
        results["steps"].append("Articles inserted with embeddings")

        # Query for similar articles
        query = "artificial intelligence and neural networks"
        similar_articles = query_similar_articles(
            weaviate_client, openai_client, collection_name, query
        )
        results["steps"].append(f"Found {len(similar_articles)} similar articles")
        results["similar_articles"] = [dict(a) for a in similar_articles]

        # Summarize results with OpenAI
        summary = summarize_with_openai(openai_client, similar_articles, query)
        results["steps"].append("Generated summary with OpenAI")
        results["summary"] = summary

    finally:
        weaviate_client.close()
        print("\nWeaviate connection closed.")

    return results


@app.route("/")
def index():
    """Home page with links to demo."""
    return """
    <h1>OpenTelemetry Tracing Demo</h1>
    <p>Weaviate + OpenAI + HTTP auto-instrumentation</p>
    <ul>
        <li><a href="/demo">Run Demo</a> - Execute the full demo workflow</li>
        <li><a href="http://localhost:16686" target="_blank">Jaeger UI</a> - View traces</li>
    </ul>
    <p>All operations are automatically traced with OpenTelemetry!</p>
    """


@app.route("/demo")
def demo():
    """Run the demo and return results as JSON."""
    print("=" * 60)
    print("OpenTelemetry Tracing Demo: Weaviate + OpenAI + HTTP")
    print("=" * 60)
    print("\nAll operations are being traced automatically!")
    print("View traces in Jaeger UI: http://localhost:16686")
    print("=" * 60)

    results = run_demo()

    print("\n" + "=" * 60)
    print("Demo completed successfully!")
    print("Check Jaeger UI at http://localhost:16686 to view traces")
    print("Look for service: weaviate-openai-demo")
    print("=" * 60)

    return jsonify(results)


@app.route("/health")
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy"})


def main():
    """Main function to run the Flask app or execute demo directly."""
    # Check if running as a script or as a web server
    run_as_server = os.getenv("RUN_AS_SERVER", "true").lower() == "true"

    if run_as_server:
        print("=" * 60)
        print("OpenTelemetry Tracing Demo Server")
        print("=" * 60)
        print("\nStarting Flask server...")
        print("Visit http://localhost:5000/demo to run the demo")
        print("View traces in Jaeger UI: http://localhost:16686")
        print("=" * 60)

        # Run Flask app
        app.run(host="0.0.0.0", port=5000, debug=False)
    else:
        # Run demo directly (traces will be separate per library call)
        print("=" * 60)
        print("OpenTelemetry Tracing Demo (Direct Mode)")
        print("=" * 60)
        print("\nNote: Running directly without Flask means traces will be separate.")
        print("For unified traces, run with RUN_AS_SERVER=true")
        print("=" * 60)

        run_demo()
        print("\nWaiting 10 seconds for traces to be exported...")
        time.sleep(10)


if __name__ == "__main__":
    main()
