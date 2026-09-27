import json
from decimal import Decimal, InvalidOperation

from common.dynamo import get_application, update_application_status
from common.logging_utils import logger

_DECLINE_THRESHOLD = Decimal("50000")


def _status_for_income(income) -> str:
    if income is None:
        return "PENDING"
    if isinstance(income, bool):
        raise ValueError("questionnaire.income must be numeric")

    try:
        amount = Decimal(str(income))
    except (InvalidOperation, TypeError, ValueError) as err:
        raise ValueError("questionnaire.income must be numeric") from err

    if not amount.is_finite():
        raise ValueError("questionnaire.income must be a finite number")
    return "DECLINED" if amount < _DECLINE_THRESHOLD else "APPROVED"


def process_sqs_batch(event):
    batch_item_failures = []

    for record in event.get("Records", []):
        message_id = record["messageId"]
        try:
            request = json.loads(record["body"])
            application_id = request["applicationId"]
            expected_updated_at = request["updatedAt"]
            application = get_application(application_id, consistent_read=True)

            if not application:
                raise ValueError(f"Application {application_id} does not exist")
            if application.get("updatedAt") != expected_updated_at:
                continue

            questionnaire = application.get("questionnaire") or {}
            status = _status_for_income(questionnaire.get("income"))
            update_application_status(application_id, status, expected_updated_at)
        except Exception:
            logger.exception("Failed to process decision engine request %s", message_id)
            batch_item_failures.append({"itemIdentifier": message_id})

    return {"batchItemFailures": batch_item_failures}
