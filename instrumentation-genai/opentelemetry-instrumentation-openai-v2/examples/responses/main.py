import os

from openai import OpenAI


def main():
    client = OpenAI()
    model = os.getenv("RESPONSES_MODEL", "gpt-4o-mini")

    response = client.responses.create(
        model=model,
        input="Write a short poem about OpenTelemetry.",
    )

    print("Responses.create")
    print(f"Model: {response.model}")
    print(f"Response ID: {response.id}")
    print(f"Output text: {response.output_text}")

    print("\nResponses.stream")
    with client.responses.stream(
        model=model,
        input="Write a short poem about OpenTelemetry.",
        background=True,
    ) as stream:
        for event in stream:
            if event.type == "response.output_text.delta":
                print(event.delta, end="", flush=True)
            if event.type == "response.completed":
                print("\n")
                print(f"Stream response ID: {event.response.id}")
                break


if __name__ == "__main__":
    main()
