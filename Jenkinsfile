pipeline {
    agent any

    parameters {
        booleanParam(
            name: 'DEPLOY',
            defaultValue: false,
            description: 'Deploy the validated commit to the dev AWS environment'
        )
    }

    environment {
        AWS_REGION = 'us-east-1'
        APP_NAME = 'questionnaire-app'
        ENVIRONMENT = 'dev'
        INFRA_STACK_NAME = 'questionnaire-app-infra-dev'
        LAMBDA_STACK_NAME = 'questionnaire-app-lambda-dev'
    }

    stages {
        stage('Install dependencies') {
            steps {
                sh '''
                    python3 -m venv .venv
                    . .venv/bin/activate
                    python -m pip install --upgrade pip
                    pip install -r lambda/requirements-dev.txt
                '''
            }
        }

        stage('Unit tests') {
            steps {
                sh '''
                    . .venv/bin/activate
                    mkdir -p reports
                    cd lambda
                    pytest -v \\
                      --junitxml=../reports/unit-tests.xml \\
                      --cov=src \\
                      --cov-report=term-missing \\
                      --cov-report=xml:../reports/coverage.xml
                '''
            }
            post {
                always {
                    junit testResults: 'reports/unit-tests.xml', allowEmptyResults: false
                }
            }
        }

        stage('SAST') {
            steps {
                sh '''
                    . .venv/bin/activate
                    mkdir -p reports
                    bandit -r lambda/src -ll -f json -o reports/bandit.json
                '''
            }
        }

        stage('Deploy') {
            when {
                expression { params.DEPLOY }
            }
            steps {
                input message: 'Validation passed. Deploy this commit to the dev AWS environment?', ok: 'Deploy'
                sh '''
                    set -eu

                    aws cloudformation deploy \\
                      --template-file infrastructure/template.yaml \\
                      --stack-name "$INFRA_STACK_NAME" \\
                      --parameter-overrides Environment="$ENVIRONMENT" AppName="$APP_NAME" \\
                      --region "$AWS_REGION" \\
                      --no-fail-on-empty-changeset

                    ECR_REPOSITORY_URI=$(aws cloudformation describe-stacks \\
                      --stack-name "$INFRA_STACK_NAME" \\
                      --region "$AWS_REGION" \\
                      --query "Stacks[0].Outputs[?OutputKey=='DecisionEngineRepositoryUri'].OutputValue" \\
                      --output text)
                    ECR_REGISTRY=$(printf '%s' "$ECR_REPOSITORY_URI" | cut -d/ -f1)
                    # BUILD_TAG may contain spaces in multibranch jobs; use a
                    # Docker-safe immutable tag instead.
                    IMAGE_URI="${ECR_REPOSITORY_URI}:jenkins-${BUILD_NUMBER}"

                    aws ecr get-login-password --region "$AWS_REGION" \\
                      | docker login --username AWS --password-stdin "$ECR_REGISTRY"
                    docker build -f lambda/Dockerfile -t "$IMAGE_URI" lambda
                    docker push "$IMAGE_URI"

                    . .venv/bin/activate
                    python -m pip install aws-sam-cli
                    sam build --template-file lambda/template.yaml --build-dir .aws-sam/build
                    sam deploy \\
                      --template-file .aws-sam/build/template.yaml \\
                      --stack-name "$LAMBDA_STACK_NAME" \\
                      --resolve-s3 \\
                      --capabilities CAPABILITY_IAM \\
                      --region "$AWS_REGION" \\
                      --parameter-overrides Environment="$ENVIRONMENT" AppName="$APP_NAME" DecisionEngineImageUri="$IMAGE_URI" \\
                      --no-fail-on-empty-changeset \\
                      --no-confirm-changeset
                '''
            }
        }

        stage('Merge PR') {
            when {
                allOf {
                    expression { params.DEPLOY }
                    changeRequest()
                }
            }
            steps {
                withCredentials([usernamePassword(
                    credentialsId: 'github-merge-token',
                    usernameVariable: 'GITHUB_USER',
                    passwordVariable: 'GITHUB_TOKEN'
                )]) {
                    sh '''
                        set -eu
                        response=$(curl --fail-with-body --silent --show-error \\
                          --request PUT \\
                          --user "$GITHUB_USER:$GITHUB_TOKEN" \\
                          --header 'Accept: application/vnd.github+json' \\
                          --header 'X-GitHub-Api-Version: 2022-11-28' \\
                          --data '{"merge_method":"squash"}' \\
                          "https://api.github.com/repos/zhongw117/questionnaire/pulls/${CHANGE_ID}/merge")

                        printf '%s' "$response" | grep -Eq '"merged"[[:space:]]*:[[:space:]]*true'
                        echo "PR #${CHANGE_ID} merged successfully; GitHub will close it."
                    '''
                }
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: 'reports/**/*', allowEmptyArchive: true
        }
        cleanup {
            sh 'rm -rf .venv'
        }
    }
}

