import abc
import inspect
import json
import re
from typing import Dict

from opentelemetry.instrumentation.botocore.extensions.types import (
    AttributeMapT,
    AwsSdkCallContext,
    AwsSdkExtension,
)
from opentelemetry.propagate import inject
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace.span import Span


class LambdaOperation(abc.ABC):
    @classmethod
    @abc.abstractmethod
    def operation_name(cls):
        pass

    @classmethod
    def prepare_attributes(
        cls, call_context: AwsSdkCallContext, attributes: AttributeMapT
    ):
        pass

    @classmethod
    def before_service_call(cls, call_context: AwsSdkCallContext, span: Span):
        pass


class OpInvoke(LambdaOperation):
    # https://docs.aws.amazon.com/lambda/latest/dg/API_Invoke.html#API_Invoke_RequestParameters
    ARN_LAMBDA_PATTERN = re.compile(
        "(?:arn:(?:aws[a-zA-Z-]*)?:lambda:)?"
        "(?:[a-z]{2}(?:-gov)?-[a-z]+-\\d{1}:)?(?:\\d{12}:)?"
        "(?:function:)?([a-zA-Z0-9-_\\.]+)(?::(?:\\$LATEST|[a-zA-Z0-9-_]+))?"
    )

    @classmethod
    def operation_name(cls):
        return "Invoke"

    @classmethod
    def extract_attributes(
        cls, call_context: AwsSdkCallContext, attributes: AttributeMapT
    ):
        attributes[SpanAttributes.FAAS_INVOKED_PROVIDER] = "aws"
        attributes[
            SpanAttributes.FAAS_INVOKED_NAME
        ] = cls._parse_function_name(call_context)
        attributes[SpanAttributes.FAAS_INVOKED_REGION] = call_context.region

    @classmethod
    def _parse_function_name(cls, call_context: AwsSdkCallContext):
        function_name_or_arn = call_context.params.get("FunctionName")
        matches = cls.ARN_LAMBDA_PATTERN.match(function_name_or_arn)
        function_name = matches.group(1)
        return function_name_or_arn if function_name is None else function_name

    @classmethod
    def before_service_call(cls, call_context: AwsSdkCallContext, span: Span):
        payload_str = call_context.params.get("Payload")
        if payload_str is None:
            return

        # TODO: reconsider this as it manipulates input of called lambda function
        payload = json.loads(payload_str)
        headers = payload.get("headers", {})
        inject(headers)
        payload["headers"] = headers
        call_context.params["Payload"] = json.dumps(payload)


################################################################################
# Lambda extension
################################################################################

_OPERATION_MAPPING = {
    op.operation_name(): op
    for op in globals().values()
    if inspect.isclass(op)
    and issubclass(op, LambdaOperation)
    and not inspect.isabstract(op)
}  # type: Dict[str, LambdaOperation]


class LambdaExtension(AwsSdkExtension):
    def __init__(self, call_context: AwsSdkCallContext):
        super().__init__(call_context)
        self._op = _OPERATION_MAPPING.get(call_context.operation)

    def extract_attributes(self, attributes: AttributeMapT):
        if self._op is None:
            return

        self._op.extract_attributes(self._call_context, attributes)

    def before_service_call(self, span: Span):
        if self._op is None:
            return

        self._op.before_service_call(self._call_context, span)
