# Questionnaire Application Service

```
Client -> API Gateway -> Lambda(Create/Update/Get, Python) -> TransUnion(Mock Lambda) -> DynamoDB
```

## 目录结构

```
project/
├── infrastructure/
│   └── template.yaml        # 数据层：DynamoDB 表（独立部署的 CFN 栈）
├── lambda/
│   ├── template.yaml        # 计算层：SAM 模板，隐式创建 API Gateway + 4 个 Lambda
│   └── src/
│       ├── common/               # 共享代码（DynamoDB 封装 / TransUnion 调用 / HTTP 响应）
│       └── handlers/
│           ├── create_application.py  # POST   /applications
│           ├── update_application.py  # PUT    /applications/{applicationId}
│           ├── get_application.py     # GET    /applications/{applicationId}
│           └── transunion_mock.py     # 被前三者以 Lambda Invoke 方式调用，非 API 路由
└── .github/workflows/deploy.yml # merge 到 main 后自动部署
```

两个 CloudFormation 栈：

- **infrastructure 栈**只有 DynamoDB 表，先部署，导出表名给 lambda 栈用。
- **lambda 栈**（CloudFormation + SAM Transform）负责 API Gateway（隐式创建）、4 个
  Lambda 及其 IAM 权限，通过 `Fn::ImportValue` 引用 infra 栈导出的表名。

四个 Lambda **共用同一份 `src/` 目录**（`CodeUri: src/`），靠不同的 `Handler`
入口区分，没有用 Lambda Layer，也没有 `requirements.txt` —— `boto3` 是 Python
Lambda 运行时自带的，项目没有其它第三方依赖，这样部署流程最少只需要
`sam build && sam deploy` 两步，不涉及 npm/pip 安装、打层这些环节。

## TransUnion Mock 的行为

`transunion_mock.py` 不挂在 API Gateway 上，是被 create/update 函数通过
`boto3` 的 `lambda.invoke()` 同步调用的一个普通 Lambda：传入 `{"userId": ...}`，
按 `userId` 字符累加值的奇偶性，稳定返回 `700` 或 `500` 的信用分（同一个
userId 每次结果一致）。调用方拿到分数后连同 questionnaire 一起存进 DynamoDB
的 `creditScore` 字段。

## API

### POST /applications
```json
{
  "applicant": { "userId": "u-001", "name": "Wilson" },
  "questionnaire": { "income": 80000, "employmentStatus": "FULL_TIME" }
}
```
返回 201，body 里包含生成的 `applicationId`、`creditScore`（700 或 500）、`status: CREATED`。

### PUT /applications/{applicationId}
```json
{
  "questionnaire": { "income": 95000, "employmentStatus": "FULL_TIME" }
}
```
会重新调用一次 TransUnion(Mock) 拿 `creditScore`，`status` 变为 `UPDATED`。
`applicationId` 不存在返回 404。

### GET /applications/{applicationId}
返回完整记录，不存在返回 404。

## 部署（最简流程，假设你已经有 AWS 账户/AK-SK）

只需要两个 GitHub Secret：`AWS_ACCESS_KEY_ID`、`AWS_SECRET_ACCESS_KEY`
（在仓库 Settings → Secrets and variables → Actions 里添加），不需要提前建
S3 bucket、不需要配 OIDC 角色 —— workflow 里用的是 `sam deploy --resolve-s3`，
SAM 会自动创建并托管一个部署用的 S3 bucket。

push 到 `main` 分支即触发 `.github/workflows/deploy.yml`：
1. `aws cloudformation deploy` 部署 `infrastructure/template.yaml`
2. `sam build && sam deploy` 部署 `lambda/template.yaml`

### 本地手动部署（可选，用于第一次验证）

```bash
# 1. 数据层
aws cloudformation deploy \
  --template-file infrastructure/template.yaml \
  --stack-name questionnaire-app-infra-dev \
  --parameter-overrides Environment=dev AppName=questionnaire-app

# 2. 计算层
cd lambda
sam build
sam deploy --guided --resolve-s3
```

`sam deploy --guided` 只在第一次跑的时候需要，之后它会把参数记在
`lambda/samconfig.toml` 里（已加入 `.gitignore`，不提交）。

## 本地调试

```bash
cd lambda
sam build
sam local start-api
curl -X POST http://127.0.0.1:3000/applications \
  -H 'Content-Type: application/json' \
  -d '{"applicant":{"userId":"u-001"},"questionnaire":{"income":80000}}'
```

> `sam local` 里跑到 create/update 函数会真的去 invoke 已部署到云上的
> `TransUnionMockFunction`（需要本机有正确的 AWS 凭证）。如果想完全离线调试，
> 可以在 `common/transunion_client.py` 里临时 mock 掉 `fetch_credit_score`。
