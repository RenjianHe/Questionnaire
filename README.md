# Questionnaire Application Service

```
Client -> API Gateway (API key required) -> Lambda(Create/Update/Get, Python)
       -> TransUnion(Mock Lambda) -> DynamoDB
```

## Project structure

```
project/
├── infrastructure/
│   └── template.yaml        # Data layer: DynamoDB table (deployed as its own CFN stack)
├── lambda/
│   ├── template.yaml        # Compute layer: SAM template — API Gateway + 4 Lambdas + API key/usage plan
│   ├── pytest.ini
│   ├── requirements-dev.txt # Test-only deps (pytest, moto, boto3) — never shipped to Lambda
│   ├── tests/
│   │   ├── conftest.py            # Shared fixtures: env vars + moto-mocked DynamoDB table
│   │   ├── test_create_application.py
│   │   ├── test_update_application.py
│   │   ├── test_get_application.py
│   │   └── test_transunion_mock.py
│   └── src/
│       ├── common/               # DynamoDB wrapper / TransUnion client / HTTP responses / logging
│       └── handlers/
│           ├── create_application.py  # POST   /applications
│           ├── update_application.py  # PUT    /applications/{applicationId}
│           ├── get_application.py     # GET    /applications/{applicationId}
│           └── transunion_mock.py     # Invoked via Lambda Invoke, not an API route
└── .github/workflows/deploy.yml # Runs tests, then deploys on merge to main
```

Two CloudFormation stacks:

- The **infrastructure stack** only contains the DynamoDB table. It's deployed first and
  exports the table name for the lambda stack to consume.
- The **lambda stack** (CloudFormation + SAM Transform) owns API Gateway (created implicitly),
  the 4 Lambda functions, and their IAM permissions, referencing the table name exported by
  the infra stack via `Fn::ImportValue`.

All four Lambdas **share the same `src/` directory** (`CodeUri: src/`) and are distinguished
only by their `Handler` entry point. There's no Lambda Layer and no runtime
`requirements.txt` — `boto3` ships with the Python Lambda runtime and this project has no
other third-party dependencies at runtime.

## TransUnion Mock behavior

`transunion_mock.py` isn't attached to API Gateway — it's a plain Lambda invoked
synchronously by the create/update functions via `boto3`'s `lambda.invoke()`. Given
`{"userId": ...}`, it returns a stable `700` or `500` credit score based on the parity of
the sum of the userId's character codes (same userId always yields the same score). The
caller stores that score together with the questionnaire into DynamoDB's `creditScore`
field.

## One application per userId

DynamoDB doesn't support unique constraints on non-key attributes, so uniqueness is
enforced with a common single-table trick: `POST /applications` first writes a
"reservation" item (`applicationId = "USER#<userId>"`) with
`ConditionExpression: attribute_not_exists(applicationId)`. If that condition fails, the
userId already has an application and the request gets a `409 Conflict` before anything
else is written. Only after the reservation succeeds does the real application item get
written; if that second write fails for any other reason, the reservation is rolled back
so the userId isn't stuck. This makes the check-and-create atomic even under concurrent
requests for the same userId.

## API

All endpoints require an `x-api-key` header (see **Authentication** below).

### POST /applications
```json
{
  "applicant": { "userId": "u-001", "name": "Wilson" },
  "questionnaire": { "income": 80000, "employmentStatus": "FULL_TIME" }
}
```
Returns 201 with the generated `applicationId`, `creditScore` (700 or 500), and `status: CREATED`.
Returns 409 if an application already exists for this `userId` — each `userId` can only
have one application (enforced with a conditional write in DynamoDB, see below).

### PUT /applications/{applicationId}
```json
{
  "questionnaire": { "income": 95000, "employmentStatus": "FULL_TIME" }
}
```
Re-queries TransUnion (Mock) for `creditScore` and sets `status` to `UPDATED`.
Returns 404 if `applicationId` doesn't exist.

### GET /applications/{applicationId}
Returns the full record, or 404 if it doesn't exist.

## Authentication (API key)

`ApplicationsApi` requires `Auth: ApiKeyRequired: true` for every method. The stack also
creates an `AWS::ApiGateway::ApiKey` and a `UsagePlan` binding it to the deployed stage.

After deploying, get the key ID from the stack output, then fetch the actual value:

```bash
KEY_ID=$(aws cloudformation describe-stacks \
  --stack-name questionnaire-app-lambda-dev \
  --query "Stacks[0].Outputs[?OutputKey=='ApiKeyId'].OutputValue" --output text)

API_KEY=$(aws apigateway get-api-key --api-key "$KEY_ID" --include-value --query value --output text)
echo "$API_KEY"
```

Include it on every request:

```bash
curl -X POST "$API_URL/applications" \
  -H "Content-Type: application/json" \
  -H "x-api-key: $API_KEY" \
  -d '{"applicant":{"userId":"u-001"},"questionnaire":{"income":80000}}'
```

Without a valid key, API Gateway rejects the request with `403 Forbidden` before it ever
reaches the Lambda function.

## Logging

Every handler (including `transunion_mock`) is wrapped with the `@log_invocation`
decorator from `common/logging_utils.py`, which logs the full incoming event and the full
outgoing response to CloudWatch — regardless of which code path returns. Tail it with:

```bash
aws logs tail /aws/lambda/questionnaire-app-dev-create-application --since 10m --follow
```

You'll see `REQUEST: {...}` and `RESPONSE: {...}` log lines for each invocation.

## Unit tests

Tests live in `lambda/tests/` and use `pytest` + `moto` (mocks DynamoDB — no AWS account,
no deployed stack, no network calls needed). The TransUnion call is stubbed with
`unittest.mock.patch` instead of actually invoking a Lambda.

```bash
cd lambda
pip install -r requirements-dev.txt
pytest -v
```

Covers: successful create/update/get, missing/invalid request bodies, missing `userId`,
application-not-found (404), and TransUnion mock stability/range. CI (`deploy.yml`) runs
this same `pytest` step before touching AWS — a failing test blocks deployment.

## Deployment (simplest path, assuming you already have an AWS account/access keys)

Only two GitHub Secrets are needed: `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`
(add them under repo Settings → Secrets and variables → Actions). No need to pre-create
an S3 bucket, and no need to set up an OIDC role — the workflow uses
`sam deploy --resolve-s3`, which lets SAM create and manage a deployment S3 bucket
automatically.

Pushing to `main` triggers `.github/workflows/deploy.yml`:
1. Install deps and run `pytest`
2. `aws cloudformation deploy` deploys `infrastructure/template.yaml`
3. `sam build && sam deploy` deploys `lambda/template.yaml`

### Manual local deployment (optional, for first-time verification)

```bash
# 1. Data layer
aws cloudformation deploy \
  --template-file infrastructure/template.yaml \
  --stack-name questionnaire-app-infra-dev \
  --parameter-overrides Environment=dev AppName=questionnaire-app

# 2. Compute layer
cd lambda
sam build
sam deploy --guided --resolve-s3
```

`sam deploy --guided` is only needed the first time — after that it records the
parameters in `lambda/samconfig.toml` (already in `.gitignore`, not committed).

## Local debugging against deployed AWS resources

```bash
cd lambda
sam build
sam local start-api
curl -X POST http://127.0.0.1:3000/applications \
  -H 'Content-Type: application/json' \
  -d '{"applicant":{"userId":"u-001"},"questionnaire":{"income":80000}}'
```

> `sam local` bypasses the API key check (it's an API Gateway feature, not enforced
> locally), and the create/update functions will actually invoke the already-deployed
> `TransUnionMockFunction` in the cloud (requires valid AWS credentials on your machine).
> For fully offline testing, use the `pytest` suite above instead.
