from common.dynamo import get_application
from common.logging_utils import log_invocation, logger
from common import responses


@log_invocation
def handler(event, context):
    application_id = (event.get("pathParameters") or {}).get("applicationId")
    if not application_id:
        return responses.bad_request("Missing applicationId path parameter")

    try:
        item = get_application(application_id)
        if not item:
            return responses.not_found(f"application {application_id} does not exist")
        return responses.ok(item)
    except Exception as err:  # noqa: BLE001
        logger.error("Failed to fetch application: %s", err)
        return responses.internal_error("Failed to fetch application")
