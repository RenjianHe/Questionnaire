import json
from unittest.mock import patch

from handlers import create_application


@patch("handlers.create_application.fetch_credit_score", return_value=700)
def test_create_application_success(mock_fetch, dynamodb_table):
    event = {
        "body": json.dumps(
            {
                "applicant": {"userId": "u-001"},
                "questionnaire": {"income": 80000},
            }
        )
    }

    response = create_application.handler(event, None)

    assert response["statusCode"] == 201
    body = json.loads(response["body"])
    assert body["creditScore"] == 700
    assert body["status"] == "CREATED"
    assert "applicationId" in body
    mock_fetch.assert_called_once_with("u-001")


def test_create_application_missing_fields(dynamodb_table):
    event = {"body": json.dumps({"applicant": {"userId": "u-001"}})}
    response = create_application.handler(event, None)
    assert response["statusCode"] == 400


def test_create_application_missing_user_id(dynamodb_table):
    event = {
        "body": json.dumps(
            {
                "applicant": {"name": "no id here"},
                "questionnaire": {"income": 1},
            }
        )
    }
    response = create_application.handler(event, None)
    assert response["statusCode"] == 400


def test_create_application_invalid_json(dynamodb_table):
    event = {"body": "{not valid json"}
    response = create_application.handler(event, None)
    assert response["statusCode"] == 400


@patch("handlers.create_application.fetch_credit_score", return_value=700)
def test_create_application_duplicate_user_id_returns_conflict(mock_fetch, dynamodb_table):
    event = {
        "body": json.dumps(
            {
                "applicant": {"userId": "u-dup"},
                "questionnaire": {"income": 80000},
            }
        )
    }

    first_response = create_application.handler(event, None)
    assert first_response["statusCode"] == 201

    second_response = create_application.handler(event, None)
    assert second_response["statusCode"] == 409
    body = json.loads(second_response["body"])
    assert "u-dup" in body["message"]
