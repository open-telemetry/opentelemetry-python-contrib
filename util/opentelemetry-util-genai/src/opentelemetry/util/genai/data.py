from dataclasses import dataclass


@dataclass
class Message:
    content: str
    type: str
    name: str

    def _to_part_dict(self):
        """Convert the message to a dictionary suitable for OpenTelemetry semconvs.

        Ref: https://github.com/open-telemetry/semantic-conventions/blob/main/docs/registry/attributes/gen-ai.md#gen-ai-input-messages
        """

        # TODO: Support tool_call and tool_call response
        return {
            "role": self.type,
            "parts": [
                {
                    "content": self.content,
                    "type": "text",
                }
            ],
        }


@dataclass
class ChatGeneration:
    content: str
    type: str
    finish_reason: str = None


@dataclass
class Error:
    message: str
    type: type[BaseException]
