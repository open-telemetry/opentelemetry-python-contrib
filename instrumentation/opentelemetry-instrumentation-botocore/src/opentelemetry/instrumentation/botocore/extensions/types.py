from typing import Any, Dict

from opentelemetry.trace import SpanKind
from opentelemetry.trace.span import Span
from opentelemetry.util.types import AttributeValue

BotoClientT = "botocore.client.BaseClient"
BotoResultT = Dict[str, Any]
BotoClientErrorT = "botocore.exceptions.ClientError"

OperationParamsT = Dict[str, Any]

AttributeMapT = Dict[str, AttributeValue]


class AwsSdkCallContext:
    """An context object providing information about the invoked AWS service
    call.

    Args:
        service: the AWS service (e.g. s3, lambda, ...) which is called
        service_id: the name of the service in propper casing
        operation: the called operation (e.g. ListBuckets, Invoke, ...) of the
            AWS service.
        params: a dict of input parameters passed to the service operation.
        region: the AWS region in which the service call is made
        endpoint_url: the endpoint which the service operation is calling
        api_version: the API version of the called AWS service.
        span_name: the name used to create the span.
        span_kind: the kind used to create the span.
    """

    def __init__(
        self, client: BotoClientT, operation: str, params: OperationParamsT
    ):
        boto_meta = client.meta
        service_model = boto_meta.service_model

        self.service = service_model.service_name.lower()
        self.operation = operation
        self.params = params

        self.region = boto_meta.region_name  # type: str
        self.endpoint_url = boto_meta.endpoint_url  # type: str

        self.api_version = service_model.api_version  # type: str
        # name of the service in proper casing
        self.service_id = str(service_model.service_id)

        self.span_name = "{}.{}".format(self.service_id, self.operation)
        self.span_kind = SpanKind.CLIENT


class AwsSdkExtension:
    def __init__(self, call_context: AwsSdkCallContext):
        self._call_context = call_context

    def should_trace_service_call(self) -> bool:  # pylint:disable=no-self-use
        """Returns if the AWS SDK service call should be traced or not

        Extensions might override this function to disable tracing for certain
        operations.
        """
        return True

    def extract_attributes(self, attributes: AttributeMapT):
        """Callback which gets invoked before the span is created.

        Extensions might override this function to extract additional attributes.
        """

    def before_service_call(self, span: Span):
        """Callback which gets invoked after the span is created but before the
        AWS SDK service is called.

        Extensions might override this function e.g. for injecting the span into
        a carrier.
        """

    def on_success(self, span: Span, result: BotoResultT):
        """Callback that gets invoked when the AWS SDK call returns
        successfully.

        Extensions might override this function e.g. to extract and set response
        attributes on the span.
        """

    def on_error(self, span: Span, exception: BotoClientErrorT):
        """Callback that gets invoked when the AWS SDK service call raises a
        ClientError.
        """

    def after_service_call(self):
        """Callback that gets invoked after the AWS SDK service was called.

        Extensions might override this function to do some cleanup tasks.
        """
