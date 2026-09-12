import json
import os
import boto3

_lambda_client = boto3.client("lambda")
_FUNCTION_NAME = os.environ["TRANSUNION_FUNCTION_NAME"]


def fetch_credit_score(user_id: str) -> int:
    response = _lambda_client.invoke(
        FunctionName=_FUNCTION_NAME,
        InvocationType="RequestResponse",
        Payload=json.dumps({"userId": user_id}).encode("utf-8"),
    )

    if "FunctionError" in response:
        raise RuntimeError(f"TransUnion mock 调用失败: {response['FunctionError']}")

    payload = json.loads(response["Payload"].read())
    return payload["creditScore"]
