# Environment variables must be set before any handler/common module is
# imported, because common/dynamo.py and common/transunion_client.py read
# them at import time (module-level os.environ[...]).
import os

os.environ.setdefault("TABLE_NAME", "test-applications-table")
os.environ.setdefault("TRANSUNION_FUNCTION_NAME", "test-transunion-mock")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")

import boto3  # noqa: E402
import pytest  # noqa: E402
from moto import mock_aws  # noqa: E402


@pytest.fixture
def dynamodb_table():
    """Spins up a moto-mocked DynamoDB table matching the real schema."""
    with mock_aws():
        client = boto3.client("dynamodb", region_name="us-east-1")
        client.create_table(
            TableName=os.environ["TABLE_NAME"],
            KeySchema=[{"AttributeName": "applicationId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "applicationId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield
