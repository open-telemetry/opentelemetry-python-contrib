import json
import os

import boto3


def main():
    client = boto3.client("bedrock-runtime")
    response = client.invoke_model(
        modelId=os.getenv("CHAT_MODEL", "amazon.titan-text-lite-v1"),
        body=json.dumps(
            {
                "inputText": "Write a short poem on OpenTelemetry.",
                "textGenerationConfig": {},
            },
        ),
    )

    body = response["body"].read()
    response_data = json.loads(body.decode("utf-8"))
    print(response_data["results"][0]["outputText"])


if __name__ == "__main__":
    main()
