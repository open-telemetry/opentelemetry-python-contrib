# pylint: skip-file
import anthropic


def main():
    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=1024,
        messages=[
            {"role": "user", "content": "Write a short poem on OpenTelemetry."}
        ],
    )
    print(message.content[0].text)


if __name__ == "__main__":
    main()
