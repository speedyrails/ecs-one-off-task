# ECS one-off task

Creates and run a one-off ECS task from an ECS task definition already created. Also, put the container logs (stdout) to Amazon CloudWatch, wait for the task to finishes and print the container logs (stdout).

## Script Idea

The script is mainly intended to use in CI/CD pipelines to run one-off tasks like database migrations, but you can use it as a standalone script with a different command. See the usage help for further details: `ecs-one-off-task.py -h/--help`.

The idea of this script is to create a new task definition/revisions from an already task definition to run a command, e.g: database migrations, using a new application's image version. With this approach, we don't modify the current task definition for the app and we can have a separate log group on CloudWatch to record the executed task.

In order to keep the same requirements for the new task some elements need to be extracted from the reference task such as secrets (environment variables referenced from SSM Parameters), environment files (.env file in S3), environment variables defined inline in the task, and the execution role ARN.

The new task definition is created with the following manifest:

```python
{
    "executionRoleArn": execRoleArn,
    "containerDefinitions": [
        {
            "environmentFiles": [],
            "secrets": [],
            "environment": [],
            "entryPoint": [],
            "portMappings": [],
            "command": containerCommand,
            "cpu": 128,
            "memory": 400,
            "memoryReservation": 300,
            "volumesFrom": [],
            "image": containerImage,
            "name": oneOffTaskName,
            "logConfiguration": {
                "logDriver": "awslogs",
                "options": {
                    "awslogs-group": oneOffTaskContainerLogGroup,
                    "awslogs-region": awsRegion,
                    "awslogs-stream-prefix": oneOffTaskContainerLogStreamPrefix
                }
            }
        }
    ],
    "family": oneOffTaskName
}
```

Once the one-off task is registered, the script run it and wait until is stopped, the poll is every 6 seconds by default and the maximun number of attempts to be made is 100. See the [boto3 waiter `task_stopped`](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ecs.html#ECS.Waiter.TasksStopped) for further details.

## Requirements

- Python version 3+.
- For Python requirements see the `requirements.txt` file.
- The following permission are required:
  - `ecs:RunTask`
  - `ecs:RegisterTaskDefinition`
  - `ecs:DescribeTasks`
  - `ecs:DescribeTaskDefinition`
  - `iam:PassRole`
  - `logs:DescribeLogStreams`
  - `logs:PutRetentionPolicy`
  - `logs:CreateLogGroup`
  - `logs:GetLogEvents`

The following policy must be added to the IAM user before execute the script, with a user with high privileges:

1- Add the IAM Policy:

**NOTE:** check first the name of the ECS task execution role name for your ECS cluster.

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query 'Account' --output text)
ECS_TASK_EXECUTION_ROLE_NAME="ecsTaskExecutionRole"

cat <<EOF > ecs-one-off-task-script-policy.json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "AllowRunRegisterDescribeTasks",
            "Effect": "Allow",
            "Action": [
                "ecs:RunTask",
                "ecs:RegisterTaskDefinition",
                "ecs:DescribeTasks",
                "ecs:DescribeTaskDefinition"
            ],
            "Resource": "*"
        },
        {
            "Sid": "AllowPassRole",
            "Effect": "Allow",
            "Action": "iam:PassRole",
            "Resource": "arn:aws:iam::${ACCOUNT_ID}:role/${ECS_TASK_EXECUTION_ROLE_NAME}"
        },
        {
            "Sid": "AllowLogGroupOperations",
            "Effect": "Allow",
            "Action": [
                "logs:DescribeLogStreams",
                "logs:PutRetentionPolicy",
                "logs:CreateLogGroup"
            ],
            "Resource": "arn:aws:logs:*:${ACCOUNT_ID}:log-group:*"
        },
        {
            "Sid": "AllowGetEvents",
            "Effect": "Allow",
            "Action": "logs:GetLogEvents",
            "Resource": "arn:aws:logs:*:${ACCOUNT_ID}:log-group:*:log-stream:*"
        }
    ]
}
EOF

IAM_POLICY_ARN=$(aws iam create-policy --policy-name SpeedyrailsEcsOneOffTaskScript \
  --policy-document file://ecs-one-off-task-script-policy.json \
  --description "Add required permissions to run the ecs-one-off-task script." \
  --query 'Policy.Arn' --output text)
```

2- Add the IAM policy to the user/role to execute the `ecs-one-off-task` script:

For an IAM user:

```sh
aws iam attach-user-policy --policy-arn "$IAM_POLICY_ARN" --user-name <YOUR_IAM_USER_NAME>
```

For an IAM role:

```sh
aws iam attach-role-policy --policy-arn "$IAM_POLICY_ARN" --role-name <IAM_ROLE_NAME>
```

3- Be sure to executes the `ecs-one-off-task` script using your *<YOUR_IAM_USER_NAME>/<IAM_ROLE_NAME>*.

The `ECS_TASK_EXECUTION_ROLE_NAME` IAM role must allow access to read from S3 buckets and SSM Parameter Store, this is required if the task reference (`--from-task` flag) has defined environment variables from S3 and/or SSM Parameter Store. For this, the AWS managed policies `AmazonS3ReadOnlyAccess` and `AmazonSSMReadOnlyAccess` can be added to the `ECS_TASK_EXECUTION_ROLE_NAME` IAM role.

## Installation

1- Install the Python's requirements:

```bash
pip install https://raw.githubusercontent.com/speedyrails/ecs-one-off-task/master/requirements.txt
```

2- Download the script and apply the execution permissions:

```bash
curl -L https://raw.githubusercontent.com/speedyrails/ecs-one-off-task/master/ecs-one-off-task.py -o ecs-one-off-task.py
chmod +x ecs-one-off-task.py
```

For usage type: `ecs-one-off-task.py -h/--help`

## Example

To execute a database migration taking as reference an existing task definition called *myapp* on the ECS cluster *myEcsCluster* using the new application's image version *myapp:v2*:

```bash
python ecs-one-off-task.py --task-name myapp-db-migrations --from-task myapp --cluster myEcsCluster \
    --image myapp:v2 --command bundle exec rake db:migrate
```

**NOTES:**

- You can specify an AWS profile name and region using the `-p/--profile` and `-r/--region` flags respectively.
- Every time you define a new image version, a new revision will be created for the task definition `myapp-db-migrations`.
- If you need to use `&&`, `||`, `|`, `<`, `>` or the command has arguments with flags, you must specify the command between `''` or `""` and define one of the following entry points `'sh -c'` or `'bash -c'`; please noted that *the entry point always must be defined using `''` or `""`*.

## License

MIT

## Author Information

[Speedyrails Inc.](https://www.speedyrails.com/)

By: [Carlos M Bustillo Rdguez](https://linkedin.com/in/carlosbustillordguez/)
