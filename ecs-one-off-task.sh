#!/bin/bash
#
# Creates a one-off ECS task.
#
# Usage:
#   ./ecs-one-off-task.sh "TASK_NAME" "EXEC_ROLE_ARN" "ECS_CLUSTER_NAME" "OCI_IMAGE:TAG" "S3_ARN_ENV_VARS" "ENTRYPOINT" "COMMAND"
#
# Example:
#   ecs-one-off-task.sh "db-migrations" "arn:aws:iam::ACCOUNT_ID:role/ecsTaskExecutionRole" "myEcsCluster" "myapp:latest" "arn:aws:s3:::bucket/myapp-vars.env" "sh -c" "bundle exec rake db:migrate"
# 
# By Carlos Miguel Bustillo Rdguez <https://linkedin.com/in/carlosbustillordguez/>
# Speedyrails Inc. <https://www.speedyrails.com/>
#
# Version: 1.0.0 (Tue 05 Jan 2021 03:08:27 PM GMT)


### Functions

check_requirements() {

    if [ -z "$(which aws)" ]; then
        echo "The command 'aws' is not installed in the system!!"
        echo "Please follow the instructions: https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html"
        exit 1
    fi

    if [ -z "$(which jq)" ]; then
        echo "The command 'jq' is not installed in the system!!"
        echo "Please install it: apt install jq"
        exit 1
    fi

} # => check_requirements()

create_task_definition_file() {

    TASK_NAME="$1"
    EXEC_ROLE_ARN="$2"
    IMAGE_WITH_TAG="$3"
    S3_ARN_ENV_VARS="$4"
    ENTRYPOINT="$5"
    COMMAND="$6"

    # Convert ENTRYPOINT in a comma separated list
    LIST=""
    for i in $ENTRYPOINT; do
        LIST="${LIST:+$LIST }\"$i\""
    done
    # Bash pattern substitution: ${parameter//pattern/string}
    ENTRYPOINT_LIST=${LIST// /, }

    # Convert COMMAND in a comma separated list
    LIST=""
    for i in $COMMAND; do
        LIST="${LIST:+$LIST }\"$i\""
    done
    # Bash pattern substitution: ${parameter//pattern/string}
    COMMAND_LIST=${LIST// /, }

cat <<EOF > one-off-task-definition.json
{
    "executionRoleArn": "$EXEC_ROLE_ARN",
    "containerDefinitions": [
      {
        "environmentFiles": [
          {
            "value": "$S3_ARN_ENV_VARS",
            "type": "s3"
          }
        ],
        "entryPoint": [ $ENTRYPOINT_LIST ],
        "portMappings": [],
        "command": [ $COMMAND_LIST ],
        "cpu": 128,
        "memory": 400,
        "memoryReservation": 300,
        "volumesFrom": [],
        "image": "$IMAGE_WITH_TAG",
        "name": "$TASK_NAME"
      }
    ],
    "family": "$TASK_NAME"
}
EOF

} # => create_task_definition_file()

### Main Program

## Check arguments
if [ -z "$1" ] || [ -z "$2" ] || [ -z "$3" ] || [ -z "$4" ] || [ -z "$5" ] || [ -z "$6" ] || [ -z "$7" ]; then
    echo "$(basename "$0"): Missing arguments or not arguments passed."
    echo "Usage:"
    echo "  ./$(basename "$0") \"TASK_NAME\" \"EXEC_ROLE_ARN\" \"ECS_CLUSTER_NAME\" \"OCI_IMAGE:TAG\" \"S3_ARN_ENV_VARS\" \"ENTRYPOINT\" \"COMMAND\""
    echo "Example:"
    echo "  ./$(basename "$0") \"db-migrations\" \"arn:aws:iam::ACCOUNT_ID:role/ecsTaskExecutionRole\" \"myEcsCluster\" \"myapp:latest\" \"arn:aws:s3:::bucket/myapp-vars.env\" \"sh -c\" \"bundle exec rake db:migrate\""
    exit 1
else
    TASK_NAME="$1"
    EXEC_ROLE_ARN="$2"
    ECS_CLUSTER_NAME="$3"
    IMAGE_WITH_TAG="$4"
    S3_ARN_ENV_VARS="$5"
    ENTRYPOINT="$6"
    COMMAND="$7"
fi

check_requirements
create_task_definition_file "$TASK_NAME" "$EXEC_ROLE_ARN" "$IMAGE_WITH_TAG" "$S3_ARN_ENV_VARS" "$ENTRYPOINT" "$COMMAND"

# Register the task definition
TASK_OUTPUT=$(aws ecs register-task-definition --cli-input-json file://one-off-task-definition.json)

# Get the task definition ARN
TASK_DEFINITION_ARN=$(echo "$TASK_OUTPUT" | jq -r '.taskDefinition.taskDefinitionArn')

if [ -n "$TASK_OUTPUT" ]; then
    echo "Created task definition: $TASK_DEFINITION_ARN"
else
    exit 1
fi

# Get the task definition revision
TASK_DEFINITION_REVISION=$(echo "$TASK_OUTPUT" | jq -r '.taskDefinition.revision')

# Run the task definition revision
RUN_TASK_OUTPUT=$(aws ecs run-task --cluster "$ECS_CLUSTER_NAME" --task-definition "$TASK_NAME":"$TASK_DEFINITION_REVISION")

# Get the task ARN
RUN_TASK_ARN=$(echo "$RUN_TASK_OUTPUT" | jq -r '.tasks[0].taskArn')

echo "Executed task ARN: $RUN_TASK_ARN"

# Wait until the task is stopped
aws ecs wait tasks-stopped --cluster "$ECS_CLUSTER_NAME" --tasks "$RUN_TASK_ARN"

# Get the output of the stopped task
STOPPED_TASK_OUTPUT=$(aws ecs describe-tasks --cluster "$ECS_CLUSTER_NAME" --tasks "$RUN_TASK_ARN")

echo -e "The migration process has finised: \n"
echo "$STOPPED_TASK_OUTPUT"

# Get the container exit status code
CT_EXIT_STATUS_CODE="$(echo "$STOPPED_TASK_OUTPUT" | jq -r '.tasks[0].containers[0].exitCode')"

if [ "$CT_EXIT_STATUS_CODE" == "0" ]; then
    echo -e "\nThe one-off task process has finished correctly!!"
    exit 0
else
    echo -e "\nThe one-off task has failed. See the above output for further details!!"
    exit 1
fi
