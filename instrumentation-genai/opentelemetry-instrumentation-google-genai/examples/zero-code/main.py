import os
import google.genai


def main():
    client = google.genai.Client()
    response = client.models.generate_content(
        model = os.getenv('MODEL', 'gemini-2.0-flash-001'),
        contents = os.getenv('PROMPT', 'Why is the sky blue?'),
    )
    print(response.text)


if __name__ == "__main__":
    main()
