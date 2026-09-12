import json
from datetime import datetime, timezone

from common.dynamo import get_application, update_application
from common.transunion_client import fetch_credit_score
from common import responses


def handler(event, context):
    application_id = (event.get("pathParameters") or {}).get("applicationId")
    if not application_id:
        return responses.bad_request("缺少 applicationId 路径参数")

    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return responses.bad_request("请求体不是合法 JSON")

    questionnaire = body.get("questionnaire")
    if not questionnaire:
        return responses.bad_request("请求体必须包含 questionnaire 字段")

    try:
        existing = get_application(application_id)
        if not existing:
            return responses.not_found(f"application {application_id} 不存在")

        applicant = body.get("applicant") or existing.get("applicant")
        user_id = applicant.get("userId") if isinstance(applicant, dict) else None
        if not user_id:
            return responses.bad_request("applicant 必须包含 userId 字段")

        # questionnaire 变更后重新拉取一次 TransUnion 信用分
        credit_score = fetch_credit_score(user_id)
        now = datetime.now(timezone.utc).isoformat()

        updated = update_application(application_id, questionnaire, credit_score, "UPDATED", now)
        return responses.ok(updated)
    except Exception as err:  # noqa: BLE001
        if type(err).__name__ == "ConditionalCheckFailedException":
            return responses.not_found(f"application {application_id} 不存在")
        print(f"更新 application 失败: {err}")
        return responses.internal_error("更新 application 失败")
