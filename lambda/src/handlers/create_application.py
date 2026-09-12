import json
import uuid
from datetime import datetime, timezone

from common.dynamo import put_application
from common.transunion_client import fetch_credit_score
from common import responses
from common.logging_utils import log_invocation, logger


@log_invocation
def handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return responses.bad_request("Request body is not valid JSON")

    applicant = body.get("applicant")
    questionnaire = body.get("questionnaire")

    if not applicant or not questionnaire:
        return responses.bad_request("Request body must include applicant and questionnaire fields")

    user_id = applicant.get("userId") if isinstance(applicant, dict) else None
    if not user_id:
        return responses.bad_request("applicant must include a userId field")

    try:
        application_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        credit_score = fetch_credit_score(user_id)

        item = {
            "applicationId": application_id,
            "applicant": applicant,
            "questionnaire": questionnaire,
            "creditScore": credit_score,
            "status": "CREATED",
            "createdAt": now,
            "updatedAt": now,
        }

        put_application(item)
        return responses.created(item)
    except Exception as err:  # noqa: BLE001
        logger.error("Failed to create application: %s", err)
        return responses.internal_error("Failed to create application")
