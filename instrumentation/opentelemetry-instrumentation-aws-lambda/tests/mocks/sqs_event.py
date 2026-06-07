# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html
"""

MOCK_LAMBDA_SQS_EVENT = {
    "Records": [
        {
            "messageId": "059f36b4-87a3-44ab-83d2-661975830a7d",
            "receiptHandle": "AQEBwJnKyrHigUMZj6rYigCgxlaS3SLy0a...",
            "body": "Test message.",
            "attributes": {
                "ApproximateReceiveCount": "1",
                "SentTimestamp": "1545082649183",
                "SenderId": "AIDAIENQZJOLO23YVJ4VO",
                "ApproximateFirstReceiveTimestamp": "1545082649185",
            },
            "messageAttributes": {},
            "md5OfBody": "e4e68fb7bd0e697a0ae8f1bb342846b3",
            "eventSource": "aws:sqs",
            "eventSourceARN": "arn:aws:sqs:us-east-2:123456789012:my-queue",
            "awsRegion": "us-east-2",
        }
    ]
}

# SQS event with a W3C traceparent in messageAttributes to test span link extraction.
MOCK_LAMBDA_SQS_EVENT_WITH_TRACE_CONTEXT = {
    "Records": [
        {
            "messageId": "059f36b4-87a3-44ab-83d2-661975830a7d",
            "receiptHandle": "AQEBwJnKyrHigUMZj6rYigCgxlaS3SLy0a...",
            "body": "Test message.",
            "attributes": {
                "ApproximateReceiveCount": "1",
                "SentTimestamp": "1545082649183",
                "SenderId": "AIDAIENQZJOLO23YVJ4VO",
                "ApproximateFirstReceiveTimestamp": "1545082649185",
            },
            "messageAttributes": {
                "traceparent": {
                    "DataType": "String",
                    "StringValue": "00-5ce0e9a56015fec5aadfa328ae398115-ab54a98ceb1f0ad2-01",
                }
            },
            "md5OfBody": "e4e68fb7bd0e697a0ae8f1bb342846b3",
            "eventSource": "aws:sqs",
            "eventSourceARN": "arn:aws:sqs:us-east-2:123456789012:my-queue",
            "awsRegion": "us-east-2",
        }
    ]
}

# SQS event with an uppercase TRACEPARENT key to test case-insensitive extraction.
MOCK_LAMBDA_SQS_EVENT_UPPERCASE_ATTRS = {
    "Records": [
        {
            "messageId": "059f36b4-87a3-44ab-83d2-661975830a7d",
            "receiptHandle": "AQEBwJnKyrHigUMZj6rYigCgxlaS3SLy0a...",
            "body": "Test message.",
            "attributes": {
                "ApproximateReceiveCount": "1",
                "SentTimestamp": "1545082649183",
                "SenderId": "AIDAIENQZJOLO23YVJ4VO",
                "ApproximateFirstReceiveTimestamp": "1545082649185",
            },
            "messageAttributes": {
                "TRACEPARENT": {
                    "DataType": "String",
                    "StringValue": "00-5ce0e9a56015fec5aadfa328ae398115-ab54a98ceb1f0ad2-01",
                }
            },
            "md5OfBody": "e4e68fb7bd0e697a0ae8f1bb342846b3",
            "eventSource": "aws:sqs",
            "eventSourceARN": "arn:aws:sqs:us-east-2:123456789012:my-queue",
            "awsRegion": "us-east-2",
        }
    ]
}

# SQS event where messageAttributes is explicitly None (null).
MOCK_LAMBDA_SQS_EVENT_NULL_MESSAGE_ATTRS = {
    "Records": [
        {
            "messageId": "059f36b4-87a3-44ab-83d2-661975830a7d",
            "receiptHandle": "AQEBwJnKyrHigUMZj6rYigCgxlaS3SLy0a...",
            "body": "Test message.",
            "attributes": {
                "ApproximateReceiveCount": "1",
                "SentTimestamp": "1545082649183",
                "SenderId": "AIDAIENQZJOLO23YVJ4VO",
                "ApproximateFirstReceiveTimestamp": "1545082649185",
            },
            "messageAttributes": None,
            "md5OfBody": "e4e68fb7bd0e697a0ae8f1bb342846b3",
            "eventSource": "aws:sqs",
            "eventSourceARN": "arn:aws:sqs:us-east-2:123456789012:my-queue",
            "awsRegion": "us-east-2",
        }
    ]
}

# SQS event where the messageAttributes key is entirely absent from the record.
MOCK_LAMBDA_SQS_EVENT_ABSENT_MESSAGE_ATTRS = {
    "Records": [
        {
            "messageId": "059f36b4-87a3-44ab-83d2-661975830a7d",
            "receiptHandle": "AQEBwJnKyrHigUMZj6rYigCgxlaS3SLy0a...",
            "body": "Test message.",
            "attributes": {
                "ApproximateReceiveCount": "1",
                "SentTimestamp": "1545082649183",
                "SenderId": "AIDAIENQZJOLO23YVJ4VO",
                "ApproximateFirstReceiveTimestamp": "1545082649185",
            },
            "md5OfBody": "e4e68fb7bd0e697a0ae8f1bb342846b3",
            "eventSource": "aws:sqs",
            "eventSourceARN": "arn:aws:sqs:us-east-2:123456789012:my-queue",
            "awsRegion": "us-east-2",
        }
    ]
}

# Three-record batch: record 1 has no context, record 2 uses a title-case key, record 3 lowercase.
# Exactly two span links should be extracted (records 2 and 3).
MOCK_LAMBDA_SQS_BATCH_EVENT_PARTIAL_CONTEXT = {
    "Records": [
        {
            "messageId": "059f36b4-87a3-44ab-83d2-661975830a7d",
            "receiptHandle": "AQEBwJnKyrHigUMZj6rYigCgxlaS3SLy0a...",
            "body": "Test message 1 — no trace context.",
            "attributes": {
                "ApproximateReceiveCount": "1",
                "SentTimestamp": "1545082649183",
                "SenderId": "AIDAIENQZJOLO23YVJ4VO",
                "ApproximateFirstReceiveTimestamp": "1545082649185",
            },
            "messageAttributes": {},
            "md5OfBody": "e4e68fb7bd0e697a0ae8f1bb342846b3",
            "eventSource": "aws:sqs",
            "eventSourceARN": "arn:aws:sqs:us-east-2:123456789012:my-queue",
            "awsRegion": "us-east-2",
        },
        {
            "messageId": "2e1424d4-f796-459a-8184-9c92662be6da",
            "receiptHandle": "AQEBwJnKyrHigUMZj6rYigCgxlaS3SLy0b...",
            "body": "Test message 2 — title-case Traceparent.",
            "attributes": {
                "ApproximateReceiveCount": "1",
                "SentTimestamp": "1545082650636",
                "SenderId": "AIDAIENQZJOLO23YVJ4VO",
                "ApproximateFirstReceiveTimestamp": "1545082650649",
            },
            "messageAttributes": {
                "Traceparent": {
                    "DataType": "String",
                    "StringValue": "00-aabbccddeeff00112233445566778899-aabbccddeeff0011-01",
                }
            },
            "md5OfBody": "e4e68fb7bd0e697a0ae8f1bb342846b4",
            "eventSource": "aws:sqs",
            "eventSourceARN": "arn:aws:sqs:us-east-2:123456789012:my-queue",
            "awsRegion": "us-east-2",
        },
        {
            "messageId": "7a3b5c9d-1234-5678-abcd-ef0123456789",
            "receiptHandle": "AQEBwJnKyrHigUMZj6rYigCgxlaS3SLy0c...",
            "body": "Test message 3 — lowercase traceparent.",
            "attributes": {
                "ApproximateReceiveCount": "1",
                "SentTimestamp": "1545082651700",
                "SenderId": "AIDAIENQZJOLO23YVJ4VO",
                "ApproximateFirstReceiveTimestamp": "1545082651710",
            },
            "messageAttributes": {
                "traceparent": {
                    "DataType": "String",
                    "StringValue": "00-cafebabe12345678cafebabe12345678-cafebabe12345678-01",
                }
            },
            "md5OfBody": "e4e68fb7bd0e697a0ae8f1bb342846b5",
            "eventSource": "aws:sqs",
            "eventSourceARN": "arn:aws:sqs:us-east-2:123456789012:my-queue",
            "awsRegion": "us-east-2",
        },
    ]
}

# Malformed: Records list is empty — _is_sqs_event should return False.
MOCK_MALFORMED_SQS_EVENT_EMPTY_RECORDS = {"Records": []}

# Malformed: Records is a string, not a list — _is_sqs_event should return False.
MOCK_MALFORMED_SQS_EVENT_RECORDS_NOT_LIST = {"Records": "not-a-list"}

# Malformed: eventSource is "aws:s3", not "aws:sqs" — _is_sqs_event should return False.
MOCK_MALFORMED_SQS_EVENT_WRONG_SOURCE = {
    "Records": [
        {
            "messageId": "059f36b4-87a3-44ab-83d2-661975830a7d",
            "receiptHandle": "AQEBwJnKyrHigUMZj6rYigCgxlaS3SLy0a...",
            "body": "Test message.",
            "attributes": {},
            "messageAttributes": {},
            "md5OfBody": "e4e68fb7bd0e697a0ae8f1bb342846b3",
            "eventSource": "aws:s3",
            "eventSourceARN": "arn:aws:s3:::my-bucket",
            "awsRegion": "us-east-2",
        }
    ]
}

# Malformed: no Records key at all — _is_sqs_event should return False.
MOCK_MALFORMED_SQS_EVENT_NO_RECORDS_KEY = {"body": "oops, no Records key"}

# SQS event with a traceparent whose StringValue is not a valid W3C traceparent.
# The propagator will parse it as an invalid context; no span link should be extracted.
MOCK_LAMBDA_SQS_EVENT_INVALID_TRACEPARENT = {
    "Records": [
        {
            "messageId": "059f36b4-87a3-44ab-83d2-661975830a7d",
            "receiptHandle": "AQEBwJnKyrHigUMZj6rYigCgxlaS3SLy0a...",
            "body": "Test message.",
            "attributes": {
                "ApproximateReceiveCount": "1",
                "SentTimestamp": "1545082649183",
                "SenderId": "AIDAIENQZJOLO23YVJ4VO",
                "ApproximateFirstReceiveTimestamp": "1545082649185",
            },
            "messageAttributes": {
                "traceparent": {
                    "DataType": "String",
                    "StringValue": "not-a-valid-traceparent",
                }
            },
            "md5OfBody": "e4e68fb7bd0e697a0ae8f1bb342846b3",
            "eventSource": "aws:sqs",
            "eventSourceARN": "arn:aws:sqs:us-east-2:123456789012:my-queue",
            "awsRegion": "us-east-2",
        }
    ]
}

# SQS event where the messageAttributes value is a bare string rather than a dict.
# _SqsMessageAttributesGetter checks isinstance(msg_attr, Mapping), so no link is extracted.
MOCK_LAMBDA_SQS_EVENT_ATTR_NOT_DICT = {
    "Records": [
        {
            "messageId": "059f36b4-87a3-44ab-83d2-661975830a7d",
            "receiptHandle": "AQEBwJnKyrHigUMZj6rYigCgxlaS3SLy0a...",
            "body": "Test message.",
            "attributes": {
                "ApproximateReceiveCount": "1",
                "SentTimestamp": "1545082649183",
                "SenderId": "AIDAIENQZJOLO23YVJ4VO",
                "ApproximateFirstReceiveTimestamp": "1545082649185",
            },
            "messageAttributes": {
                "traceparent": "bare-string-value",
            },
            "md5OfBody": "e4e68fb7bd0e697a0ae8f1bb342846b3",
            "eventSource": "aws:sqs",
            "eventSourceARN": "arn:aws:sqs:us-east-2:123456789012:my-queue",
            "awsRegion": "us-east-2",
        }
    ]
}

# SQS event where the attribute dict has DataType but no StringValue key.
# The getter returns None for missing StringValue; no link is extracted.
MOCK_LAMBDA_SQS_EVENT_MISSING_STRING_VALUE = {
    "Records": [
        {
            "messageId": "059f36b4-87a3-44ab-83d2-661975830a7d",
            "receiptHandle": "AQEBwJnKyrHigUMZj6rYigCgxlaS3SLy0a...",
            "body": "Test message.",
            "attributes": {
                "ApproximateReceiveCount": "1",
                "SentTimestamp": "1545082649183",
                "SenderId": "AIDAIENQZJOLO23YVJ4VO",
                "ApproximateFirstReceiveTimestamp": "1545082649185",
            },
            "messageAttributes": {
                "traceparent": {"DataType": "String"},
            },
            "md5OfBody": "e4e68fb7bd0e697a0ae8f1bb342846b3",
            "eventSource": "aws:sqs",
            "eventSourceARN": "arn:aws:sqs:us-east-2:123456789012:my-queue",
            "awsRegion": "us-east-2",
        }
    ]
}

# SQS event with no eventSourceARN key; _extract_sqs_queue_name falls back to "".
# The CONSUMER span name becomes "process ".
MOCK_LAMBDA_SQS_EVENT_MISSING_ARN = {
    "Records": [
        {
            "messageId": "059f36b4-87a3-44ab-83d2-661975830a7d",
            "receiptHandle": "AQEBwJnKyrHigUMZj6rYigCgxlaS3SLy0a...",
            "body": "Test message.",
            "attributes": {
                "ApproximateReceiveCount": "1",
                "SentTimestamp": "1545082649183",
                "SenderId": "AIDAIENQZJOLO23YVJ4VO",
                "ApproximateFirstReceiveTimestamp": "1545082649185",
            },
            "messageAttributes": {},
            "md5OfBody": "e4e68fb7bd0e697a0ae8f1bb342846b3",
            "eventSource": "aws:sqs",
            "awsRegion": "us-east-2",
        }
    ]
}

# SQS event with a malformed ARN (no colons, fewer than 6 parts).
# _extract_sqs_queue_name returns the full string; CONSUMER span name becomes "process bad-arn".
MOCK_LAMBDA_SQS_EVENT_SHORT_ARN = {
    "Records": [
        {
            "messageId": "059f36b4-87a3-44ab-83d2-661975830a7d",
            "receiptHandle": "AQEBwJnKyrHigUMZj6rYigCgxlaS3SLy0a...",
            "body": "Test message.",
            "attributes": {
                "ApproximateReceiveCount": "1",
                "SentTimestamp": "1545082649183",
                "SenderId": "AIDAIENQZJOLO23YVJ4VO",
                "ApproximateFirstReceiveTimestamp": "1545082649185",
            },
            "messageAttributes": {},
            "md5OfBody": "e4e68fb7bd0e697a0ae8f1bb342846b3",
            "eventSource": "aws:sqs",
            "eventSourceARN": "bad-arn",
            "awsRegion": "us-east-2",
        }
    ]
}

# SQS event with two records to test batch attribute handling.
MOCK_LAMBDA_SQS_BATCH_EVENT = {
    "Records": [
        {
            "messageId": "059f36b4-87a3-44ab-83d2-661975830a7d",
            "receiptHandle": "AQEBwJnKyrHigUMZj6rYigCgxlaS3SLy0a...",
            "body": "Test message 1.",
            "attributes": {
                "ApproximateReceiveCount": "1",
                "SentTimestamp": "1545082649183",
                "SenderId": "AIDAIENQZJOLO23YVJ4VO",
                "ApproximateFirstReceiveTimestamp": "1545082649185",
            },
            "messageAttributes": {
                "traceparent": {
                    "DataType": "String",
                    "StringValue": "00-5ce0e9a56015fec5aadfa328ae398115-ab54a98ceb1f0ad2-01",
                }
            },
            "md5OfBody": "e4e68fb7bd0e697a0ae8f1bb342846b3",
            "eventSource": "aws:sqs",
            "eventSourceARN": "arn:aws:sqs:us-east-2:123456789012:my-queue",
            "awsRegion": "us-east-2",
        },
        {
            "messageId": "2e1424d4-f796-459a-8184-9c92662be6da",
            "receiptHandle": "AQEBwJnKyrHigUMZj6rYigCgxlaS3SLy0b...",
            "body": "Test message 2.",
            "attributes": {
                "ApproximateReceiveCount": "1",
                "SentTimestamp": "1545082650636",
                "SenderId": "AIDAIENQZJOLO23YVJ4VO",
                "ApproximateFirstReceiveTimestamp": "1545082650649",
            },
            "messageAttributes": {
                "traceparent": {
                    "DataType": "String",
                    "StringValue": "00-8a3c60f7d188f8fa79d48a391a778fa6-53995c3f42cd8ad8-01",
                }
            },
            "md5OfBody": "e4e68fb7bd0e697a0ae8f1bb342846b4",
            "eventSource": "aws:sqs",
            "eventSourceARN": "arn:aws:sqs:us-east-2:123456789012:my-queue",
            "awsRegion": "us-east-2",
        },
    ]
}
