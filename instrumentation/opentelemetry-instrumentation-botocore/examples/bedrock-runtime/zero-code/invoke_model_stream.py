import json
import os

import boto3


def main():
    chat_model = os.getenv("CHAT_MODEL", "amazon.titan-text-lite-v1")
    prompt = "Write a short poem on OpenTelemetry."
    if "amazon.titan" in chat_model:
        body = {
            "inputText": prompt,
            "textGenerationConfig": {},
        }
    elif "amazon.nova" in chat_model:
        body = {
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "schemaVersion": "messages-v1",
        }
    elif "anthropic.claude" in chat_model:
        body = {
            "messages": [
                {"role": "user", "content": [{"text": prompt, "type": "text"}]}
            ],
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 200,
        }
    else:
        raise ValueError()
    client = boto3.client("bedrock-runtime")
    response = client.invoke_model_with_response_stream(
        modelId=chat_model,
        body=json.dumps(body),
    )

    answer = ""
    for event in response["body"]:
        json_bytes = event.get("chunk", {}).get("bytes", b"")
        decoded = json_bytes.decode("utf-8")
        chunk = json.loads(decoded)
        if "outputText" in chunk:
            answer += chunk["outputText"]
        elif "completion" in chunk:
            answer += chunk["completion"]
        elif "contentBlockDelta" in chunk:
            answer += chunk["contentBlockDelta"]["delta"]["text"]
    print(answer)


if __name__ == "__main__":
    main()
