"""
https://docs.aws.amazon.com/lambda/latest/dg/with-ddb.html
"""

MOCK_LAMBDA_DYNAMO_DB_EVENT = {
    "Records": [
        {
            "eventID": "1",
            "eventVersion": "1.0",
            "dynamodb": {
                "Keys": {"Id": {"N": "101"}},
                "NewImage": {
                    "Message": {"S": "New item!"},
                    "Id": {"N": "101"},
                },
                "StreamViewType": "NEW_AND_OLD_IMAGES",
                "SequenceNumber": "111",
                "SizeBytes": 26,
            },
            "awsRegion": "us-west-2",
            "eventName": "INSERT",
            "eventSourceARN": "arn:aws:dynamodb:us-east-2:123456789012:table/my-table/stream/2023-06-10T19:26:16.525",
            "eventSource": "aws:dynamodb",
        },
        {
            "eventID": "2",
            "eventVersion": "1.0",
            "dynamodb": {
                "OldImage": {
                    "Message": {"S": "New item!"},
                    "Id": {"N": "101"},
                },
                "SequenceNumber": "222",
                "Keys": {"Id": {"N": "101"}},
                "SizeBytes": 59,
                "NewImage": {
                    "Message": {"S": "This item has changed"},
                    "Id": {"N": "101"},
                },
                "StreamViewType": "NEW_AND_OLD_IMAGES",
            },
            "awsRegion": "us-west-2",
            "eventName": "MODIFY",
            "eventSourceARN": "arn:aws:dynamodb:us-east-2:123456789012:table/my-table/stream/2023-06-10T19:26:16.525",
            "eventSource": "aws:dynamodb",
        },
    ]
}
