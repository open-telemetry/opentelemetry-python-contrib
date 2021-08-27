import importlib
import logging

from opentelemetry.instrumentation.botocore.extensions.types import (
    AwsSdkCallContext,
    AwsSdkExtension,
)

logger = logging.getLogger(__name__)


def _lazy_load(module, cls):
    def loader():
        imported_mod = importlib.import_module(module, __name__)
        return getattr(imported_mod, cls, None)

    return loader


_KNOWN_EXTENSIONS = {
    "dynamodb": _lazy_load(".dynamodb", "DynamoDbExtension"),
    "lambda": _lazy_load(".lmbd", "LambdaExtension"),
    "sqs": _lazy_load(".sqs", "SqsExtension"),
}


def find_extension(call_context: AwsSdkCallContext) -> AwsSdkExtension:
    try:
        loader = _KNOWN_EXTENSIONS.get(call_context.service)
        if loader is None:
            return AwsSdkExtension(call_context)

        extension_cls = loader()
        return extension_cls(call_context)
    except Exception as ex:  # pylint: disable=broad-except
        logger.warning("Error when loading extension: %s", ex)
        return AwsSdkExtension(call_context)
