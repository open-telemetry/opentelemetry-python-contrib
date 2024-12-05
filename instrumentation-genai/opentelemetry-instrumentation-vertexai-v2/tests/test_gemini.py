import pytest
from vertexai.preview.generative_models import GenerativeModel, Part

# from opentelemetry.semconv_ai import SpanAttributes


@pytest.mark.vcr
def test_vertexai_generate_content(exporter):
    multimodal_model = GenerativeModel("gemini-pro-vision")
    multimodal_model.generate_content(
        [
            Part.from_uri(
                "gs://generativeai-downloads/images/scones.jpg",
                mime_type="image/jpeg",
            ),
            "what is shown in this image?",
        ]
    )

    spans = exporter.get_finished_spans()
    assert [span.name for span in spans] == [
        "text_completion gemini-pro-vision"
    ]

    vertexai_span = spans[0]
    assert len(spans) == 1

    assert dict(vertexai_span.attributes) == {
        "gen_ai.system": "vertex_ai",
        "gen_ai.operation.name": "text_completion",
        "gen_ai.request.model": "gemini-pro-vision",
        "gen_ai.response.model": "gemini-pro-vision",
        "gen_ai.usage.output_tokens": 31,
        "gen_ai.usage.input_tokens": 265,
    }

    # TODO: verify Events
