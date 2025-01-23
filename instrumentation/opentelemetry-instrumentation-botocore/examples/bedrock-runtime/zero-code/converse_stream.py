import os

import boto3


def main():
    client = boto3.client("bedrock-runtime")
    stream = client.converse_stream(
        modelId=os.getenv("CHAT_MODEL", "amazon.titan-text-lite-v1"),
        messages=[
            {
                "role": "user",
                "content": [{"text": "Write a short poem on OpenTelemetry."}],
            },
        ],
    )

    response = ""
    for s in stream["stream"]:
        if "contentBlockDelta" in s:
            response += s["contentBlockDelta"]["delta"]["text"]
    print(response)


if __name__ == "__main__":
    main()
