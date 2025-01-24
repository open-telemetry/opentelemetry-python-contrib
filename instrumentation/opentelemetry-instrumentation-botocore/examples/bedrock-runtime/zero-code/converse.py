import os

import boto3


def main():
    client = boto3.client("bedrock-runtime")
    response = client.converse(
        modelId=os.getenv("CHAT_MODEL", "amazon.titan-text-lite-v1"),
        messages=[
            {
                "role": "user",
                "content": [{"text": "Write a short poem on OpenTelemetry."}],
            },
        ],
    )

    print(response["output"]["message"]["content"][0]["text"])


if __name__ == "__main__":
    main()
