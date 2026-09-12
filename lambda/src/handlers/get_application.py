from common.dynamo import get_application
from common import responses


def handler(event, context):
    application_id = (event.get("pathParameters") or {}).get("applicationId")
    if not application_id:
        return responses.bad_request("缺少 applicationId 路径参数")

    try:
        item = get_application(application_id)
        if not item:
            return responses.not_found(f"application {application_id} 不存在")
        return responses.ok(item)
    except Exception as err:  # noqa: BLE001
        print(f"查询 application 失败: {err}")
        return responses.internal_error("查询 application 失败")
