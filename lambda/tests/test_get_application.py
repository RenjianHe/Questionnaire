import json

from handlers import get_application
from common.dynamo import put_application


def test_get_existing_application(dynamodb_table):
    item = {
        "applicationId": "abc-123",
        "applicant": {"userId": "u-001"},
        "questionnaire": {"income": 80000},
        "status": "PENDING",
        "createdAt": "2026-01-01T00:00:00+00:00",
        "updatedAt": "2026-01-01T00:00:00+00:00",
    }
    put_application(item)

    event = {"pathParameters": {"applicationId": "abc-123"}}
    response = get_application.handler(event, None)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["applicationId"] == "abc-123"
    assert body["status"] == "PENDING"


def test_get_missing_application(dynamodb_table):
    event = {"pathParameters": {"applicationId": "does-not-exist"}}
    response = get_application.handler(event, None)
    assert response["statusCode"] == 404


def test_get_missing_path_param(dynamodb_table):
    response = get_application.handler({"pathParameters": {}}, None)
    assert response["statusCode"] == 400
