from typing import Any, Dict

from opentelemetry.trace import SpanKind

_BotoClientT = "botocore.client.BaseClient"

_OperationParamsT = Dict[str, Any]


class _AwsSdkCallContext:
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
        self, client: _BotoClientT, operation: str, params: _OperationParamsT
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
