import json
from decimal import Decimal
from unittest.mock import patch

import pytest

from common.dynamo import get_application, put_application
from handlers import decision_engine, worker


def _seed_application(income, updated_at="2026-01-01T00:00:00+00:00"):
    item = {
        "applicationId": "abc-123",
        "applicant": {"userId": "u-001"},
        "questionnaire": {} if income is None else {"income": income},
        "status": "PENDING",
        "createdAt": updated_at,
        "updatedAt": updated_at,
    }
    put_application(item)
    return item


def _event(updated_at="2026-01-01T00:00:00+00:00"):
    return {
        "Records": [
            {
                "messageId": "message-1",
                "body": json.dumps(
                    {"applicationId": "abc-123", "updatedAt": updated_at}
                ),
            }
        ]
    }


@pytest.mark.parametrize(
    ("income", "expected_status"),
    [
        (None, "PENDING"),
        (Decimal("49999.99"), "DECLINED"),
        (50000, "APPROVED"),
        (80000, "APPROVED"),
    ],
)
def test_decision_engine_updates_application_status(income, expected_status, dynamodb_table):
    _seed_application(income)

    response = decision_engine.process_sqs_batch(_event())

    assert response == {"batchItemFailures": []}
    assert get_application("abc-123")["status"] == expected_status


def test_decision_engine_does_not_apply_stale_decision(dynamodb_table):
    _seed_application(80000, updated_at="2026-01-01T00:00:00+00:00")
    put_application(
        {
            "applicationId": "abc-123",
            "applicant": {"userId": "u-001"},
            "questionnaire": {"income": 10000},
            "status": "PENDING",
            "createdAt": "2026-01-01T00:00:00+00:00",
            "updatedAt": "2026-01-02T00:00:00+00:00",
        }
    )

    response = decision_engine.process_sqs_batch(_event())

    assert response == {"batchItemFailures": []}
    assert get_application("abc-123")["status"] == "PENDING"


def test_decision_engine_retries_invalid_income_message(dynamodb_table):
    _seed_application("not-a-number")

    response = decision_engine.process_sqs_batch(_event())

    assert response == {"batchItemFailures": [{"itemIdentifier": "message-1"}]}
    assert get_application("abc-123")["status"] == "PENDING"


def test_worker_only_deletes_successfully_processed_messages():
    class FakeSqsClient:
        def __init__(self):
            self.deleted = []

        def receive_message(self, **kwargs):
            assert kwargs == {
                "QueueUrl": "queue-url",
                "MaxNumberOfMessages": 10,
                "WaitTimeSeconds": 20,
            }
            return {
                "Messages": [
                    {"MessageId": "ok", "Body": "{}", "ReceiptHandle": "receipt-ok"},
                    {"MessageId": "retry", "Body": "{}", "ReceiptHandle": "receipt-retry"},
                ]
            }

        def delete_message(self, **kwargs):
            self.deleted.append(kwargs)

    sqs_client = FakeSqsClient()

    def process_batch(event):
        assert [r["messageId"] for r in event["Records"]] == ["ok", "retry"]
        return {"batchItemFailures": [{"itemIdentifier": "retry"}]}

    with patch("handlers.worker.process_sqs_batch", side_effect=process_batch):
        worker.poll_once(sqs_client, "queue-url")

    assert sqs_client.deleted == [
        {"QueueUrl": "queue-url", "ReceiptHandle": "receipt-ok"}
    ]
