import json
import uuid
from datetime import datetime, timezone

from common.dynamo import put_application_for_user, UserAlreadyExistsError
from common.decision_engine_client import publish_decision_request
from common.logging_utils import log_invocation, logger
from common import responses


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

        item = {
            "applicationId": application_id,
            "applicant": applicant,
            "questionnaire": questionnaire,
            "status": "PENDING",
            "createdAt": now,
            "updatedAt": now,
        }

        put_application_for_user(item, user_id)
        publish_decision_request(application_id, now)
        return responses.created(item)
    except UserAlreadyExistsError as err:
        return responses.conflict(str(err))
    except Exception as err:  # noqa: BLE001
        logger.error("Failed to create application: %s", err)
        return responses.internal_error("Failed to create application")
