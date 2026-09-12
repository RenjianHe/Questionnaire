import os
import boto3

_dynamodb = boto3.resource("dynamodb")
_table = _dynamodb.Table(os.environ["TABLE_NAME"])


def put_application(item: dict) -> dict:
    _table.put_item(Item=item)
    return item


def get_application(application_id: str) -> dict | None:
    result = _table.get_item(Key={"applicationId": application_id})
    return result.get("Item")


def update_application(application_id: str, questionnaire: dict, credit_score: int, status: str, now: str) -> dict:
    result = _table.update_item(
        Key={"applicationId": application_id},
        ConditionExpression="attribute_exists(applicationId)",
        UpdateExpression=(
            "SET questionnaire = :questionnaire, creditScore = :creditScore, "
            "#status = :status, updatedAt = :updatedAt"
        ),
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={
            ":questionnaire": questionnaire,
            ":creditScore": credit_score,
            ":status": status,
            ":updatedAt": now,
        },
        ReturnValues="ALL_NEW",
    )
    return result["Attributes"]
