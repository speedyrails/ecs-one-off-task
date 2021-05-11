# ECS one-off task

Creates a one-off ECS task.

## Requirements

- The `aws` command line must be installed on the system. See [Installing, updating, and uninstalling the AWS CLI version 2](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html) in the AWS documentation for further details.
- The command line tool [jq](https://stedolan.github.io/jq/). For Debian/Ubuntu distros: `apt install jq`.

The following AWS IAM permission are required to execute the script commands:

- `ecs:RunTask`
- `ecs:RegisterTaskDefinition`
- `ecs:DescribeTasks`
- `iam:PassRole`

IAM Policy example:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "AllowRunRegisterDescribeTasks",
            "Effect": "Allow",
            "Action": [
                "ecs:RunTask",
                "ecs:RegisterTaskDefinition",
                "ecs:DescribeTasks"
            ],
            "Resource": "*"
        },
        {
            "Sid": "AllowPassRole",
            "Effect": "Allow",
            "Action": "iam:PassRole",
            "Resource": "arn:aws:iam::<ACCOUNT_ID>:role/ecsTaskExecutionRole"
        }
    ]
}
```

The `ecsTaskExecutionRole` IAM role must allow access to read from S3 buckets, this is required to load the container environment variables in the task definition. For this, the AWS managed policy `AmazonS3ReadOnlyAccess` can be added to the `ecsTaskExecutionRole` IAM role.

## Usage

Download the script and apply the execution permissions:

```bash
curl -L https://raw.githubusercontent.com/speedyrails/ecs-one-off-task/master/bash-version/ecs-one-off-task.sh \
    -o ecs-one-off-task.sh
chmod +x ecs-one-off-task.sh
```

The script spects for the following arguments:

- `TASK_NAME`: ECS definition task name.
- `EXEC_ROLE_ARN`: ECS execution role for the task. The role must allow read only access to AWS S3 (AWS IAM Managed Policy `AmazonS3ReadOnlyAccess`).
- `ECS_CLUSTER_NAME`: ECS Cluster name.
- `OCI_IMAGE:TAG`: the OCI image to use for the container task.
- `S3_ARN_ENV_VARS`: the AWS S3 ARN with the required environment variables for the container.
- `COMMAND_ENTRYPOINT`: the entrypoint used by the container.
- `COMMAND_ARGUMENT`: the command passed to the container's entrypoint.

To execute the task for database migrations:

```bash
./ecs-one-off-task.sh "TASK_NAME" "EXEC_ROLE_ARN" "ECS_CLUSTER_NAME" "OCI_IMAGE:TAG" "S3_ARN_ENV_VARS" "ENTRYPOINT" "COMMAND"
```

## Example

To run a database migration:

```bash
./ecs-one-off-task.sh "db-migrations" "arn:aws:iam::<ACCOUNT_ID>:role/ecsTaskExecutionRole" "myEcsCluster" "myapp:latest" "arn:aws:s3:::bucket/myapp-vars.env" "sh -c" "bundle exec rake db:migrate"
```

## License

MIT

## Author Information

[Speedyrails Inc.](https://www.speedyrails.com/)

By: [Carlos M Bustillo Rdguez](https://linkedin.com/in/carlosbustillordguez/)
