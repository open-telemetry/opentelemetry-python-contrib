from opentelemetry.util.genai.types import (
    InputMessage,
    OutputMessage,
    Text,
    WorkflowInvocation,
)


class TestWorkflowInvocation:  # pylint: disable=no-self-use
    def test_default_values(self):
        invocation = WorkflowInvocation()
        assert invocation.name == ""
        assert invocation.operation_name == "invoke_workflow"
        assert not invocation.input_messages
        assert not invocation.output_messages
        assert invocation.span is None
        assert invocation.context_token is None
        assert not invocation.attributes

    def test_custom_name(self):
        invocation = WorkflowInvocation(name="customer_support_pipeline")
        assert invocation.name == "customer_support_pipeline"

    def test_with_input_messages(self):
        msg = InputMessage(role="user", parts=[Text(content="hello")])
        invocation = WorkflowInvocation(input_messages=[msg])
        assert len(invocation.input_messages) == 1
        assert invocation.input_messages[0].role == "user"

    def test_with_output_messages(self):
        msg = OutputMessage(
            role="assistant", parts=[Text(content="hi")], finish_reason="stop"
        )
        invocation = WorkflowInvocation(output_messages=[msg])
        assert len(invocation.output_messages) == 1
        assert invocation.output_messages[0].finish_reason == "stop"

    def test_inherits_genai_invocation(self):
        invocation = WorkflowInvocation(attributes={"key": "value"})
        assert invocation.attributes == {"key": "value"}

    def test_default_lists_are_independent(self):
        """Ensure default factory creates separate list instances."""
        inv1 = WorkflowInvocation()
        inv2 = WorkflowInvocation()
        inv1.input_messages.append(InputMessage(role="user", parts=[]))
        assert len(inv2.input_messages) == 0

    def test_default_attributes_are_independent(self):
        inv1 = WorkflowInvocation()
        inv2 = WorkflowInvocation()
        inv1.attributes["foo"] = "bar"
        assert "foo" not in inv2.attributes

    def test_full_construction(self):
        inp = InputMessage(role="user", parts=[Text(content="query")])
        out = OutputMessage(
            role="assistant",
            parts=[Text(content="answer")],
            finish_reason="stop",
        )
        invocation = WorkflowInvocation(
            name="my_workflow",
            operation_name="invoke_workflow",
            input_messages=[inp],
            output_messages=[out],
        )
        assert invocation.name == "my_workflow"
        assert len(invocation.input_messages) == 1
        assert len(invocation.output_messages) == 1
        assert invocation.output_messages[0].parts[0].content == "answer"
