import abc
import inspect
import json
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse

from opentelemetry.instrumentation.botocore.extensions.types import (
    AttributeMapT,
    AwsSdkCallContext,
    AwsSdkExtension,
    BotoResultT,
)
from opentelemetry.semconv.trace import DbSystemValues, SpanAttributes
from opentelemetry.trace.span import Span
from opentelemetry.util.types import AttributeValue

_AttributePathT = Union[str, Tuple[str]]


# converter functions


def _conv_val_to_single_attr_tuple(value: str) -> Tuple[str]:
    return None if value is None else (value,)


def _conv_dict_to_key_tuple(value: Dict[str, Any]) -> Optional[Tuple[str]]:
    return tuple(value.keys()) if isinstance(value, Dict) else None


def _conv_list_to_json_list(value: List) -> Optional[List[str]]:
    return (
        [json.dumps(item) for item in value]
        if isinstance(value, List)
        else None
    )


def _conv_val_to_single_json_tuple(value: str) -> Optional[Tuple[str]]:
    return (json.dumps(value),) if value is not None else None


def _conv_dict_to_json_str(value: Dict) -> Optional[str]:
    return json.dumps(value) if isinstance(value, Dict) else None


def _conv_val_to_len(value) -> Optional[int]:
    return len(value) if value is not None else None


################################################################################
# common request attributes
################################################################################

_REQ_TABLE_NAME = ("TableName", _conv_val_to_single_attr_tuple)
_REQ_REQITEMS_TABLE_NAMES = ("RequestItems", _conv_dict_to_key_tuple)


_REQ_GLOBAL_SEC_INDEXES = ("GlobalSecondaryIndexes", _conv_list_to_json_list)
_REQ_LOCAL_SEC_INDEXES = ("LocalSecondaryIndexes", _conv_list_to_json_list)

_REQ_PROV_READ_CAP = (("ProvisionedThroughput", "ReadCapacityUnits"), None)
_REQ_PROV_WRITE_CAP = (("ProvisionedThroughput", "WriteCapacityUnits"), None)

_REQ_CONSISTENT_READ = ("ConsistentRead", None)
_REQ_PROJECTION = ("ProjectionExpression", None)
_REQ_ATTRS_TO_GET = ("AttributesToGet", None)
_REQ_LIMIT = ("Limit", None)
_REQ_SELECT = ("Select", None)
_REQ_INDEX_NAME = ("IndexName", None)


################################################################################
# common response attributes
################################################################################

_RES_CONSUMED_CAP = ("ConsumedCapacity", _conv_list_to_json_list)
_RES_CONSUMED_CAP_SINGLE = ("ConsumedCapacity", _conv_val_to_single_json_tuple)
_RES_ITEM_COL_METRICS = ("ItemCollectionMetrics", _conv_dict_to_json_str)

################################################################################
# DynamoDB operations with enhanced attributes
################################################################################

_AttrSpecT = Tuple[_AttributePathT, Optional[Callable]]


class DynamoDbOperation(abc.ABC):
    request_attributes = None  # type: Optional[Dict[str, _AttrSpecT]]
    response_attributes = None  # type: Optional[Dict[str, _AttrSpecT]]

    @classmethod
    @abc.abstractmethod
    def operation_name(cls):
        pass

    @classmethod
    def add_start_attributes(
        cls, call_context: AwsSdkCallContext, attributes: AttributeMapT
    ):
        pass

    @classmethod
    def add_response_attributes(
        cls, call_context: AwsSdkCallContext, span: Span, result: BotoResultT
    ):
        pass


class OpBatchGetItem(DynamoDbOperation):
    request_attributes = {
        SpanAttributes.AWS_DYNAMODB_TABLE_NAMES: _REQ_REQITEMS_TABLE_NAMES,
    }
    response_attributes = {
        SpanAttributes.AWS_DYNAMODB_CONSUMED_CAPACITY: _RES_CONSUMED_CAP,
    }

    @classmethod
    def operation_name(cls):
        return "BatchGetItem"


class OpBatchWriteItem(DynamoDbOperation):
    request_attributes = {
        SpanAttributes.AWS_DYNAMODB_TABLE_NAMES: _REQ_REQITEMS_TABLE_NAMES,
    }
    response_attributes = {
        SpanAttributes.AWS_DYNAMODB_CONSUMED_CAPACITY: _RES_CONSUMED_CAP,
        SpanAttributes.AWS_DYNAMODB_ITEM_COLLECTION_METRICS: _RES_ITEM_COL_METRICS,
    }

    @classmethod
    def operation_name(cls):
        return "BatchWriteItem"


class OpCreateTable(DynamoDbOperation):
    request_attributes = {
        SpanAttributes.AWS_DYNAMODB_TABLE_NAMES: _REQ_TABLE_NAME,
        SpanAttributes.AWS_DYNAMODB_GLOBAL_SECONDARY_INDEXES: _REQ_GLOBAL_SEC_INDEXES,
        SpanAttributes.AWS_DYNAMODB_LOCAL_SECONDARY_INDEXES: _REQ_LOCAL_SEC_INDEXES,
        SpanAttributes.AWS_DYNAMODB_PROVISIONED_READ_CAPACITY: _REQ_PROV_READ_CAP,
        SpanAttributes.AWS_DYNAMODB_PROVISIONED_WRITE_CAPACITY: _REQ_PROV_WRITE_CAP,
    }

    @classmethod
    def operation_name(cls):
        return "CreateTable"


class OpDeleteItem(DynamoDbOperation):
    request_attributes = {
        SpanAttributes.AWS_DYNAMODB_TABLE_NAMES: _REQ_TABLE_NAME,
    }
    response_attributes = {
        SpanAttributes.AWS_DYNAMODB_CONSUMED_CAPACITY: _RES_CONSUMED_CAP_SINGLE,
        SpanAttributes.AWS_DYNAMODB_ITEM_COLLECTION_METRICS: _RES_ITEM_COL_METRICS,
    }

    @classmethod
    def operation_name(cls):
        return "DeleteItem"


class OpDeleteTable(DynamoDbOperation):
    request_attributes = {
        SpanAttributes.AWS_DYNAMODB_TABLE_NAMES: _REQ_TABLE_NAME,
    }

    @classmethod
    def operation_name(cls):
        return "DeleteTable"


class OpDescribeTable(DynamoDbOperation):
    request_attributes = {
        SpanAttributes.AWS_DYNAMODB_TABLE_NAMES: _REQ_TABLE_NAME,
    }

    @classmethod
    def operation_name(cls):
        return "DescribeTable"


class OpGetItem(DynamoDbOperation):
    request_attributes = {
        SpanAttributes.AWS_DYNAMODB_TABLE_NAMES: _REQ_TABLE_NAME,
        SpanAttributes.AWS_DYNAMODB_CONSISTENT_READ: _REQ_CONSISTENT_READ,
        SpanAttributes.AWS_DYNAMODB_PROJECTION: _REQ_PROJECTION,
    }
    response_attributes = {
        SpanAttributes.AWS_DYNAMODB_CONSUMED_CAPACITY: _RES_CONSUMED_CAP_SINGLE,
    }

    @classmethod
    def operation_name(cls):
        return "GetItem"


class OpListTables(DynamoDbOperation):
    request_attributes = {
        SpanAttributes.AWS_DYNAMODB_EXCLUSIVE_START_TABLE: (
            "ExclusiveStartTableName",
            None,
        ),
        SpanAttributes.AWS_DYNAMODB_LIMIT: _REQ_LIMIT,
    }
    response_attributes = {
        SpanAttributes.AWS_DYNAMODB_TABLE_COUNT: (
            "TableNames",
            _conv_val_to_len,
        ),
    }

    @classmethod
    def operation_name(cls):
        return "ListTables"


class OpPutItem(DynamoDbOperation):
    request_attributes = {
        SpanAttributes.AWS_DYNAMODB_TABLE_NAMES: _REQ_TABLE_NAME
    }
    response_attributes = {
        SpanAttributes.AWS_DYNAMODB_CONSUMED_CAPACITY: _RES_CONSUMED_CAP_SINGLE,
        SpanAttributes.AWS_DYNAMODB_ITEM_COLLECTION_METRICS: _RES_ITEM_COL_METRICS,
    }

    @classmethod
    def operation_name(cls):
        return "PutItem"


class OpQuery(DynamoDbOperation):
    request_attributes = {
        SpanAttributes.AWS_DYNAMODB_TABLE_NAMES: _REQ_TABLE_NAME,
        SpanAttributes.AWS_DYNAMODB_SCAN_FORWARD: ("ScanIndexForward", None),
        SpanAttributes.AWS_DYNAMODB_ATTRIBUTES_TO_GET: _REQ_ATTRS_TO_GET,
        SpanAttributes.AWS_DYNAMODB_CONSISTENT_READ: _REQ_CONSISTENT_READ,
        SpanAttributes.AWS_DYNAMODB_INDEX_NAME: _REQ_INDEX_NAME,
        SpanAttributes.AWS_DYNAMODB_LIMIT: _REQ_LIMIT,
        SpanAttributes.AWS_DYNAMODB_PROJECTION: _REQ_PROJECTION,
        SpanAttributes.AWS_DYNAMODB_SELECT: _REQ_SELECT,
    }
    response_attributes = {
        SpanAttributes.AWS_DYNAMODB_CONSUMED_CAPACITY: _RES_CONSUMED_CAP_SINGLE,
    }

    @classmethod
    def operation_name(cls):
        return "Query"


class OpScan(DynamoDbOperation):
    request_attributes = {
        SpanAttributes.AWS_DYNAMODB_TABLE_NAMES: _REQ_TABLE_NAME,
        SpanAttributes.AWS_DYNAMODB_SEGMENT: ("Segment", None),
        SpanAttributes.AWS_DYNAMODB_TOTAL_SEGMENTS: ("TotalSegments", None),
        SpanAttributes.AWS_DYNAMODB_ATTRIBUTES_TO_GET: _REQ_ATTRS_TO_GET,
        SpanAttributes.AWS_DYNAMODB_CONSISTENT_READ: _REQ_CONSISTENT_READ,
        SpanAttributes.AWS_DYNAMODB_INDEX_NAME: _REQ_INDEX_NAME,
        SpanAttributes.AWS_DYNAMODB_LIMIT: _REQ_LIMIT,
        SpanAttributes.AWS_DYNAMODB_PROJECTION: _REQ_PROJECTION,
        SpanAttributes.AWS_DYNAMODB_SELECT: _REQ_SELECT,
    }
    response_attributes = {
        SpanAttributes.AWS_DYNAMODB_COUNT: ("Count", None),
        SpanAttributes.AWS_DYNAMODB_SCANNED_COUNT: ("ScannedCount", None),
        SpanAttributes.AWS_DYNAMODB_CONSUMED_CAPACITY: _RES_CONSUMED_CAP_SINGLE,
    }

    @classmethod
    def operation_name(cls):
        return "Scan"


class OpUpdateItem(DynamoDbOperation):
    request_attributes = {
        SpanAttributes.AWS_DYNAMODB_TABLE_NAMES: _REQ_TABLE_NAME,
    }
    response_attributes = {
        SpanAttributes.AWS_DYNAMODB_CONSUMED_CAPACITY: _RES_CONSUMED_CAP_SINGLE,
        SpanAttributes.AWS_DYNAMODB_ITEM_COLLECTION_METRICS: _RES_ITEM_COL_METRICS,
    }

    @classmethod
    def operation_name(cls):
        return "UpdateItem"


class OpUpdateTable(DynamoDbOperation):
    request_attributes = {
        SpanAttributes.AWS_DYNAMODB_TABLE_NAMES: _REQ_TABLE_NAME,
        SpanAttributes.AWS_DYNAMODB_ATTRIBUTE_DEFINITIONS: (
            "AttributeDefinitions",
            _conv_list_to_json_list,
        ),
        SpanAttributes.AWS_DYNAMODB_GLOBAL_SECONDARY_INDEX_UPDATES: (
            "GlobalSecondaryIndexUpdates",
            _conv_list_to_json_list,
        ),
        SpanAttributes.AWS_DYNAMODB_PROVISIONED_READ_CAPACITY: _REQ_PROV_READ_CAP,
        SpanAttributes.AWS_DYNAMODB_PROVISIONED_WRITE_CAPACITY: _REQ_PROV_WRITE_CAP,
    }

    @classmethod
    def operation_name(cls):
        return "UpdateTable"


################################################################################
# DynamoDB extension
################################################################################

_OPERATION_MAPPING = {
    op.operation_name(): op
    for op in globals().values()
    if inspect.isclass(op)
    and issubclass(op, DynamoDbOperation)
    and not inspect.isabstract(op)
}  # type: Dict[str, DynamoDbOperation]


class DynamoDbExtension(AwsSdkExtension):
    def __init__(self, call_context: AwsSdkCallContext):
        super().__init__(call_context)
        self._op = _OPERATION_MAPPING.get(call_context.operation)

    def extract_attributes(self, attributes: AttributeMapT):
        attributes[SpanAttributes.DB_SYSTEM] = DbSystemValues.DYNAMODB.value
        attributes[SpanAttributes.DB_OPERATION] = self._call_context.operation
        attributes[SpanAttributes.NET_PEER_NAME] = self._get_peer_name()

        if self._op is None:
            return

        def attr_setter(key: str, value: AttributeValue):
            attributes[key] = value

        self._add_attributes(
            self._call_context.params, self._op.request_attributes, attr_setter
        )

    def _get_peer_name(self) -> str:
        return urlparse(self._call_context.endpoint_url).netloc

    def on_success(self, span: Span, result: BotoResultT):
        if not span.is_recording():
            return

        if self._op is None:
            return

        self._add_attributes(
            result, self._op.response_attributes, span.set_attribute
        )

    def _add_attributes(
        self,
        provider: Dict[str, Any],
        attributes: Dict[str, _AttrSpecT],
        setter: Callable[[str, AttributeValue], None],
    ):
        if attributes is None:
            return

        for attr_key, attr_spec in attributes.items():
            attr_path, converter = attr_spec
            value = self._get_attr_value(provider, attr_path)
            if value is None:
                continue
            if converter is not None:
                value = converter(value)
            if value is None:
                continue
            setter(attr_key, value)

    @staticmethod
    def _get_attr_value(provider: Dict[str, Any], attr_path: _AttributePathT):
        if isinstance(attr_path, str):
            return provider.get(attr_path)

        value = provider
        for path_part in attr_path:
            value = value.get(path_part)
            if value is None:
                return None

        return None if value is provider else value
