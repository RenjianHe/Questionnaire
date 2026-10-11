import os
import time

import boto3

from common.logging_utils import logger
from handlers.decision_engine import process_sqs_batch

_sqs_client = boto3.client("sqs")
_RETRY_DELAYS_SECONDS = (1, 2, 4)


def poll_once(sqs_client, queue_url: str) -> None:
    response = sqs_client.receive_message(
        QueueUrl=queue_url,
        MaxNumberOfMessages=10,
        WaitTimeSeconds=20,
    )
    messages = response.get("Messages", [])
    if not messages:
        return

    pending_messages = messages
    for attempt in range(len(_RETRY_DELAYS_SECONDS) + 1):
        result = process_sqs_batch(
            {
                "Records": [
                    {"messageId": message["MessageId"], "body": message["Body"]}
                    for message in pending_messages
                ]
            }
        )
        failed_ids = {
            failure["itemIdentifier"] for failure in result["batchItemFailures"]
        }
        successful_messages = [
            message
            for message in pending_messages
            if message["MessageId"] not in failed_ids
        ]
        pending_messages = [
            message
            for message in pending_messages
            if message["MessageId"] in failed_ids
        ]

        for message in successful_messages:
            sqs_client.delete_message(
                QueueUrl=queue_url,
                ReceiptHandle=message["ReceiptHandle"],
            )

        if not pending_messages:
            break
        if attempt < len(_RETRY_DELAYS_SECONDS):
            delay = _RETRY_DELAYS_SECONDS[attempt]
            logger.warning(
                "Retrying %s failed decision engine message(s) in %s seconds",
                len(pending_messages),
                delay,
            )
            time.sleep(delay)
        else:
            logger.error(
                "Exhausted immediate retries for %s decision engine message(s)",
                len(pending_messages),
            )


def main() -> None:
    logger.info("Starting decision engine SQS worker")
    queue_url = os.environ["DECISION_ENGINE_QUEUE_URL"]
    while True:
        poll_once(_sqs_client, queue_url)


if __name__ == "__main__":
    main()
