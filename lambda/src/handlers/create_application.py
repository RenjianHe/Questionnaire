import json
import uuid
from datetime import datetime, timezone

from common.dynamo import put_application
from common.transunion_client import fetch_credit_score
from common import responses


def handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return responses.bad_request("请求体不是合法 JSON")

    applicant = body.get("applicant")
    questionnaire = body.get("questionnaire")

    if not applicant or not questionnaire:
        return responses.bad_request("请求体必须包含 applicant 和 questionnaire 字段")

    user_id = applicant.get("userId") if isinstance(applicant, dict) else None
    if not user_id:
        return responses.bad_request("applicant 必须包含 userId 字段")

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
        print(f"创建 application 失败: {err}")
        return responses.internal_error("创建 application 失败")
