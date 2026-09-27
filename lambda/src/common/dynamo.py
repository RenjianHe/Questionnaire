import os
import boto3

_dynamodb = boto3.resource("dynamodb")
_table = _dynamodb.Table(os.environ["TABLE_NAME"])

# Prefix used for the "reservation" item that enforces one application per
# userId. Reuses the same table/partition key so no extra table/GSI is
# needed. UUIDs used for real applicationId values never collide with this.
_USER_LOCK_PREFIX = "USER#"


class UserAlreadyExistsError(Exception):
    def __init__(self, user_id: str):
        super().__init__(f"An application already exists for userId '{user_id}'")
        self.user_id = user_id


def put_application(item: dict) -> dict:
    _table.put_item(Item=item)
    return item


def put_application_for_user(item: dict, user_id: str) -> dict:
    """Creates the application item while enforcing that only one application
    can exist per userId. A conditional put on a reservation item
    (applicationId = USER#<userId>) makes the check-and-create step atomic,
    so two concurrent requests for the same userId can't both succeed."""
    lock_key = f"{_USER_LOCK_PREFIX}{user_id}"

    try:
        _table.put_item(
            Item={"applicationId": lock_key, "userId": user_id, "applicationId_ref": item["applicationId"]},
            ConditionExpression="attribute_not_exists(applicationId)",
        )
    except _table.meta.client.exceptions.ConditionalCheckFailedException as err:
        raise UserAlreadyExistsError(user_id) from err

    try:
        _table.put_item(Item=item)
    except Exception:
        # Roll back the reservation so this userId isn't permanently stuck
        _table.delete_item(Key={"applicationId": lock_key})
        raise

    return item


def get_application(application_id: str, consistent_read: bool = False) -> dict | None:
    result = _table.get_item(
        Key={"applicationId": application_id},
        ConsistentRead=consistent_read,
    )
    return result.get("Item")


def update_application(application_id: str, questionnaire: dict, status: str, now: str) -> dict:
    result = _table.update_item(
        Key={"applicationId": application_id},
        ConditionExpression="attribute_exists(applicationId)",
        UpdateExpression=(
            "SET questionnaire = :questionnaire, #status = :status, updatedAt = :updatedAt "
            "REMOVE creditScore"
        ),
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={
            ":questionnaire": questionnaire,
            ":status": status,
            ":updatedAt": now,
        },
        ReturnValues="ALL_NEW",
    )
    return result["Attributes"]


def update_application_status(application_id: str, status: str, expected_updated_at: str) -> bool:
    try:
        _table.update_item(
            Key={"applicationId": application_id},
            ConditionExpression="attribute_exists(applicationId) AND updatedAt = :expected_updated_at",
            UpdateExpression="SET #status = :status",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":expected_updated_at": expected_updated_at,
                ":status": status,
            },
        )
    except _table.meta.client.exceptions.ConditionalCheckFailedException:
        return False

    return True
