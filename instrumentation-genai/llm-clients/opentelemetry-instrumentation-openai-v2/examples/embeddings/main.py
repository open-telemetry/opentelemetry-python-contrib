import os

from openai import OpenAI


def main():
    client = OpenAI()

    # Create embeddings with OpenAI API
    embedding_response = client.embeddings.create(
        model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
        input="OpenTelemetry provides observability for your applications.",
    )

    # Print embedding information
    print(f"Model: {embedding_response.model}")
    print(f"Dimensions: {len(embedding_response.data[0].embedding)}")
    print(
        f"Token usage - Prompt: {embedding_response.usage.prompt_tokens}, Total: {embedding_response.usage.total_tokens}"
    )

    # Print a sample of the embedding vector (first 5 dimensions)
    print(
        f"Embedding sample (first 5 dimensions): {embedding_response.data[0].embedding[:5]}"
    )


if __name__ == "__main__":
    main()
