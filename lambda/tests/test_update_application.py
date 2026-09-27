import json
from unittest.mock import patch

from handlers import update_application
from common.dynamo import put_application


def _seed_application():
    item = {
        "applicationId": "abc-123",
        "applicant": {"userId": "u-001"},
        "questionnaire": {"income": 80000},
        "creditScore": 500,
        "status": "APPROVED",
        "createdAt": "2026-01-01T00:00:00+00:00",
        "updatedAt": "2026-01-01T00:00:00+00:00",
    }
    put_application(item)
    return item


@patch("handlers.update_application.publish_decision_request")
def test_update_application_success(mock_publish, dynamodb_table):
    _seed_application()

    event = {
        "pathParameters": {"applicationId": "abc-123"},
        "body": json.dumps({"questionnaire": {"income": 95000}}),
    }
    response = update_application.handler(event, None)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["status"] == "PENDING"
    assert body["questionnaire"]["income"] == 95000
    assert "creditScore" not in body
    mock_publish.assert_called_once_with(body["applicationId"], body["updatedAt"])


def test_update_application_not_found(dynamodb_table):
    event = {
        "pathParameters": {"applicationId": "does-not-exist"},
        "body": json.dumps({"questionnaire": {"income": 1}}),
    }
    response = update_application.handler(event, None)
    assert response["statusCode"] == 404


def test_update_application_missing_questionnaire(dynamodb_table):
    _seed_application()
    event = {"pathParameters": {"applicationId": "abc-123"}, "body": json.dumps({})}
    response = update_application.handler(event, None)
    assert response["statusCode"] == 400


def test_update_application_missing_path_param(dynamodb_table):
    event = {"body": json.dumps({"questionnaire": {"income": 1}})}
    response = update_application.handler(event, None)
    assert response["statusCode"] == 400
