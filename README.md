# Questionnaire Application Service

```
Client -> API Gateway -> Lambda(Create/Update/Get, Python) -> TransUnion(Mock Lambda) -> DynamoDB
```

## Project structure

```
project/
├── infrastructure/
│   └── template.yaml        # Data layer: DynamoDB table (deployed as its own CFN stack)
├── lambda/
│   ├── template.yaml        # Compute layer: SAM template, implicitly creates API Gateway + 4 Lambdas
│   └── src/
│       ├── common/               # Shared code (DynamoDB wrapper / TransUnion client / HTTP responses)
│       └── handlers/
│           ├── create_application.py  # POST   /applications
│           ├── update_application.py  # PUT    /applications/{applicationId}
│           ├── get_application.py     # GET    /applications/{applicationId}
│           └── transunion_mock.py     # Invoked by the three handlers above via Lambda Invoke, not an API route
└── .github/workflows/deploy.yml # Auto-deploys on merge to main
```

Two CloudFormation stacks:

- The **infrastructure stack** only contains the DynamoDB table. It's deployed first and
  exports the table name for the lambda stack to consume.
- The **lambda stack** (CloudFormation + SAM Transform) owns API Gateway (created implicitly),
  the 4 Lambda functions, and their IAM permissions, referencing the table name exported by
  the infra stack via `Fn::ImportValue`.

All four Lambdas **share the same `src/` directory** (`CodeUri: src/`) and are distinguished
only by their `Handler` entry point. There's no Lambda Layer and no `requirements.txt` —
`boto3` ships with the Python Lambda runtime and this project has no other third-party
dependencies, so the deployment flow is just `sam build && sam deploy`, with no npm/pip
install or layer packaging steps involved.

## TransUnion Mock behavior

`transunion_mock.py` isn't attached to API Gateway — it's a plain Lambda invoked
synchronously by the create/update functions via `boto3`'s `lambda.invoke()`. Given
`{"userId": ...}`, it returns a stable `700` or `500` credit score based on the parity of
the sum of the userId's character codes (same userId always yields the same score). The
caller stores that score together with the questionnaire into DynamoDB's `creditScore`
field.

## API

### POST /applications
```json
{
  "applicant": { "userId": "u-001", "name": "Wilson" },
  "questionnaire": { "income": 80000, "employmentStatus": "FULL_TIME" }
}
```
Returns 201 with the generated `applicationId`, `creditScore` (700 or 500), and `status: CREATED`.

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

## Deployment (simplest path, assuming you already have an AWS account/access keys)

Only two GitHub Secrets are needed: `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`
(add them under repo Settings → Secrets and variables → Actions). No need to pre-create
an S3 bucket, and no need to set up an OIDC role — the workflow uses
`sam deploy --resolve-s3`, which lets SAM create and manage a deployment S3 bucket
automatically.

Pushing to `main` triggers `.github/workflows/deploy.yml`:
1. `aws cloudformation deploy` deploys `infrastructure/template.yaml`
2. `sam build && sam deploy` deploys `lambda/template.yaml`

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

## Local debugging

```bash
cd lambda
sam build
sam local start-api
curl -X POST http://127.0.0.1:3000/applications \
  -H 'Content-Type: application/json' \
  -d '{"applicant":{"userId":"u-001"},"questionnaire":{"income":80000}}'
```

> When running locally, the create/update functions will actually invoke the
> already-deployed `TransUnionMockFunction` in the cloud (requires valid AWS credentials
> on your machine). For fully offline debugging, temporarily mock out
> `fetch_credit_score` in `common/transunion_client.py`.
