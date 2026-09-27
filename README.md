# Questionnaire Application Service

```
Client -> API Gateway (API key required) -> Lambda(Create/Update/Get, Python) -> DynamoDB
       -> SNS -> SQS -> decision engine Fargate worker -> DynamoDB
```

## Project structure

```
project/
├── infrastructure/
│   └── template.yaml        # Data layer: DynamoDB table (deployed as its own CFN stack)
├── lambda/
│   ├── template.yaml        # Compute layer: SAM — API Gateway/Lambdas + decision engine ECS/Fargate service
│   ├── Dockerfile           # Decision engine worker container image
│   ├── requirements.txt     # Decision engine worker runtime dependencies
│   ├── pytest.ini
│   ├── requirements-dev.txt # Test-only deps (pytest, moto, boto3) — never shipped to Lambda
│   ├── tests/
│   │   ├── conftest.py            # Shared fixtures: env vars + moto-mocked DynamoDB table
│   │   ├── test_create_application.py
│   │   ├── test_update_application.py
│   │   ├── test_get_application.py
│   │   └── test_decision_engine.py
│   └── src/
│       ├── common/               # DynamoDB wrapper / decision publisher / HTTP responses / logging
│       └── handlers/
│           ├── create_application.py  # POST   /applications
│           ├── update_application.py  # PUT    /applications/{applicationId}
│           ├── get_application.py     # GET    /applications/{applicationId}
│           ├── decision_engine.py     # Decision logic
│           └── worker.py              # Long-polling SQS process for ECS
└── .github/workflows/deploy.yml # Runs tests, then deploys on merge to main
```

Two CloudFormation stacks:

- the **infrastructure stack** contains DynamoDB, the decision engine ECR repository, and networking
  for the worker's public subnets. It's deployed first and exports resource names to the
  compute stack.
- the **lambda stack** (CloudFormation + SAM Transform) owns API Gateway (created implicitly),
  the API Lambdas, SNS/SQS resources, and the ECS/Fargate decision engine service and its IAM roles.

The API Lambdas share `src/` (`CodeUri: src/`). The decision engine worker is packaged as a Docker
image and runs as an ECS Fargate service.

## Asynchronous decision engine

Create and update write the application to DynamoDB with `status: PENDING`, then publish
its application ID and update timestamp to SNS. SNS delivers the event to an SQS queue,
which is long-polled by a separate ECS Fargate worker service (one task minimum, five
maximum). A visible backlog of 10 or more messages triggers scale-out; CPU target tracking
scales the service back in when the workers become idle. The worker reads the current questionnaire
and sets status to `DECLINED` when `income` is below 50000, `APPROVED` at or above 50000,
and leaves it `PENDING` when `income` is missing. Stale requests are ignored so an older
decision cannot overwrite a more recent questionnaire update. Failed messages retry and
are routed to a dead-letter queue after five receives. The service runs in public subnets
with no inbound security-group rules and needs outbound HTTPS access to AWS APIs.

The decision engine currently applies the configured rules locally.

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
Returns 201 with the generated `applicationId` and `status: PENDING`. The final decision
is applied asynchronously and is available through GET.
Returns 409 if an application already exists for this `userId` — each `userId` can only
have one application (enforced with a conditional write in DynamoDB, see below).

### PUT /applications/{applicationId}
```json
{
  "questionnaire": { "income": 95000, "employmentStatus": "FULL_TIME" }
}
```
Sets `status` to `PENDING`, publishes a new decision request, and returns without
waiting for the decision.
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

API handlers are wrapped with the `@log_invocation`
decorator from `common/logging_utils.py`, which logs the full incoming event and the full
outgoing response to CloudWatch — regardless of which code path returns. Tail it with:

```bash
aws logs tail /aws/lambda/questionnaire-app-dev-create-application --since 10m --follow
```

You'll see `REQUEST: {...}` and `RESPONSE: {...}` log lines for each invocation.

## Unit tests

Tests live in `lambda/tests/` and use `pytest` + `moto` (mocks DynamoDB — no AWS account,
no deployed stack, no network calls needed). SNS publishing is stubbed in API tests, and
the decision engine is tested against the mocked table.

```bash
cd lambda
pip install -r requirements-dev.txt
pytest -v
```

Covers: successful create/update/get, missing/invalid request bodies, missing `userId`,
application-not-found (404), decision thresholds, missing income, and stale requests.
CI (`deploy.yml`) runs this same `pytest` step before touching AWS — a failing test blocks deployment.

## Deployment (simplest path, assuming you already have an AWS account/access keys)

The GitHub Actions identity needs CloudFormation/SAM deployment permissions, permission to
pass the ECS task roles and create the Application Auto Scaling service-linked role, and ECR
image upload permissions (`ecr:GetAuthorizationToken` plus repository upload actions). Configure
`AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` under repo Settings → Secrets and variables
→ Actions. No need to pre-create
an S3 bucket, and no need to set up an OIDC role — the workflow uses
`sam deploy --resolve-s3`, which lets SAM create and manage a deployment S3 bucket
automatically.

Pushing to `main` triggers `.github/workflows/deploy.yml`:
1. Install deps and run `pytest`
2. `aws cloudformation deploy` deploys `infrastructure/template.yaml`
3. CI builds and pushes the decision engine worker image to ECR
4. `sam build && sam deploy` deploys the API Lambdas and Fargate service in `lambda/template.yaml`

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

For manual deployment, build and push an image to the ECR repository exported by the
infrastructure stack, then pass its immutable URI as the `DecisionEngineImageUri` parameter to
`sam deploy`. `sam deploy --guided` is only needed the first time — after that it records
the parameters in `lambda/samconfig.toml` (already in `.gitignore`, not committed).

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
> locally). Create/update publish decision requests to the deployed SNS topic; for fully
> offline testing, use the `pytest` suite above instead.
