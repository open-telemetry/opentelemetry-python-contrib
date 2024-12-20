import vertexai
from vertexai.generative_models import GenerativeModel


def main():
    vertexai.init()
    model = GenerativeModel("gemini-1.5-flash-002")
    chat_completion = model.generate_content(
        "Write a short poem on OpenTelemetry."
    )
    print(chat_completion.text)


if __name__ == "__main__":
    main()
