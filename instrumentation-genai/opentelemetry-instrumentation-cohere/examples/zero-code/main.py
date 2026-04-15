# pylint: skip-file
import cohere


def main():
    client = cohere.ClientV2()
    response = client.chat(
        model="command-r-plus",
        messages=[
            {"role": "user", "content": "Write a short poem on OpenTelemetry."}
        ],
    )
    print(response.message.content[0].text)


if __name__ == "__main__":
    main()
