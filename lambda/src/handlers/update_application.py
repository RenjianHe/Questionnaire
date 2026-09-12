import json
from datetime import datetime, timezone

from common.dynamo import get_application, update_application
from common.transunion_client import fetch_credit_score
from common.logging_utils import log_invocation, logger
from common import responses


@log_invocation
def handler(event, context):
    application_id = (event.get("pathParameters") or {}).get("applicationId")
    if not application_id:
        return responses.bad_request("Missing applicationId path parameter")

    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return responses.bad_request("Request body is not valid JSON")

    questionnaire = body.get("questionnaire")
    if not questionnaire:
        return responses.bad_request("Request body must include a questionnaire field")

    try:
        existing = get_application(application_id)
        if not existing:
            return responses.not_found(f"application {application_id} does not exist")

        applicant = body.get("applicant") or existing.get("applicant")
        user_id = applicant.get("userId") if isinstance(applicant, dict) else None
        if not user_id:
            return responses.bad_request("applicant must include a userId field")

        # Re-fetch the TransUnion credit score whenever the questionnaire changes
        credit_score = fetch_credit_score(user_id)
        now = datetime.now(timezone.utc).isoformat()

        updated = update_application(application_id, questionnaire, credit_score, "UPDATED", now)
        return responses.ok(updated)
    except Exception as err:  # noqa: BLE001
        if type(err).__name__ == "ConditionalCheckFailedException":
            return responses.not_found(f"application {application_id} does not exist")
        logger.error("Failed to update application: %s", err)
        return responses.internal_error("Failed to update application")