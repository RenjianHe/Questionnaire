import os

import boto3

from common.logging_utils import logger
from handlers.decision_engine import process_sqs_batch

_sqs_client = boto3.client("sqs")


def poll_once(sqs_client, queue_url: str) -> None:
    response = sqs_client.receive_message(
        QueueUrl=queue_url,
        MaxNumberOfMessages=10,
        WaitTimeSeconds=20,
    )
    messages = response.get("Messages", [])
    if not messages:
        return

    result = process_sqs_batch(
        {
            "Records": [
                {"messageId": message["MessageId"], "body": message["Body"]}
                for message in messages
            ]
        }
    )
    failed_ids = {
        failure["itemIdentifier"] for failure in result["batchItemFailures"]
    }

    for message in messages:
        if message["MessageId"] not in failed_ids:
            sqs_client.delete_message(
                QueueUrl=queue_url,
                ReceiptHandle=message["ReceiptHandle"],
            )


def main() -> None:
    logger.info("Starting decision engine SQS worker")
    queue_url = os.environ["DECISION_ENGINE_QUEUE_URL"]
    while True:
        poll_once(_sqs_client, queue_url)


if __name__ == "__main__":
    main()
