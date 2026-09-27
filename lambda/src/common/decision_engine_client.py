import json
import os

import boto3

_sns_client = boto3.client("sns")


def publish_decision_request(application_id: str, updated_at: str) -> None:
    _sns_client.publish(
        TopicArn=os.environ["DECISION_ENGINE_TOPIC_ARN"],
        Message=json.dumps(
            {
                "applicationId": application_id,
                "updatedAt": updated_at,
            }
        ),
    )
