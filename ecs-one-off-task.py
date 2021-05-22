#!/usr/bin/env python3

""" Creates and run a one-off ECS task from a task definition already created.

        For usage type: ecs-one-off-task.py -h/--help

   By Carlos Bustillo <carlos@speedyrails.com>
"""

import boto3
import argparse
import sys
import textwrap

from botocore.exceptions import ProfileNotFound


def initializeAwsClients(options):
    """ Initialize the AWS clients.

        Args:
            args: the script options.
    """
    # AWS Profile to perform the operations
    awsProfile = options.profile
    awsRegionOpt = options.region

    # Global variables
    global ecs
    global logs
    global awsRegion

    # Configured the session for the boto client
    if awsProfile and awsRegionOpt:
        try:
            session = boto3.Session(
                profile_name=awsProfile,
                region_name=awsRegionOpt
            )
        except ProfileNotFound as e:
            print(f"{sys.argv[0]} error: " + str(e))
            sys.exit(1)
    elif awsProfile:
        try:
            session = boto3.Session(profile_name=awsProfile)
        except ProfileNotFound as e:
            print(f"{sys.argv[0]} error: " + str(e))
            sys.exit(1)
    elif awsRegionOpt:
        session = boto3.Session(region_name=awsRegionOpt)
        if awsRegionOpt not in session.get_available_regions('ecs'):
            print(f"{sys.argv[0]} error: the specified region {awsRegionOpt} is not a valid AWS region")
            sys.exit(1)
    else:
        session = boto3.Session()

    # Create the ECS client
    ecs = session.client('ecs')

    # Create the CloudWatch Logs client
    logs = session.client('logs')

    # Get the AWS region for the current session
    awsRegion = session.region_name


def createCloudWatchLogGroup(logGroupName, retentionDays=7):
    """ Creates a AWS CloudWatch Log Group if doesn't exists with retation days by defualt the 7 days.

        Args:
            logGroupName: the AWS CloudWatch Log Group name to create.
            retentionDays: the number of days to retain the log events in the specified log group.
                           Possible values are: 1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365,
                           400, 545, 731, 1827, and 3653.
                           Set to None to never expire the events in the log group.
    """

    try:
        # Create the log group logGroupName
        logs.create_log_group(logGroupName=logGroupName)

        # Set the retention policy for logGroupName
        logs.put_retention_policy(
            logGroupName=logGroupName,
            retentionInDays=retentionDays
        )
    except logs.exceptions.ResourceAlreadyExistsException:
        pass

    return f"Using the '{logGroupName}' CloudWatch Log Group to store the containers logs"


def printContainerOutput(logGroupName, taskArn):
    """ Get the logs of the latest log stream in an CloudWatch Log Group.

        Args:
            logGroupName: the AWS CloudWatch Log Group name to create.

    """

    # Get the task ID from the taskArn to build the logStreamName
    taskId = taskArn.split('/')[2]

    # Log stream name of the current task
    logStreamName = logGroupName.lstrip('/') + "/" + taskId

    # Get the logs from logStreamName
    try:
        response = logs.get_log_events(
            logGroupName=logGroupName,
            logStreamName=logStreamName,
            startFromHead=False
        )

    except logs.exceptions.ResourceNotFoundException:
        print("Container output: None")
        return

    logStreamEvents = response['events']

    # Print the container logs
    if logStreamEvents:
        print("Container output: ")
        for event in logStreamEvents:
            print(event['message'])
    else:
        print("Container output: None")


def createRunTaskDefinition(options):
    """ Creates and runs new task definition from an already existing task definition.

        Args:
            args: the script options.
    """

    # ECS Cluster to connect to
    ecsCluster = options.cluster
    # One-off task parameters
    refTaskDefName = options.from_task
    containerCommand = options.command
    containerEntrypoint = options.entrypoint
    containerImage = options.image
    oneOffTaskName = options.task_name
    oneOffTaskLaunchType = options.launch_type
    oneOffTaskNetsId = options.networks_id
    oneOffTaskSgsId = options.security_groups_id
    # Container log group name and log stream prefix for CloudWatch
    oneOffTaskContainerLogGroup = f"/ecs/{oneOffTaskName}"
    oneOffTaskContainerLogStreamPrefix = "ecs"

    # Check if the network configuration is provided when the launch type is FARGATE
    if oneOffTaskLaunchType == "FARGATE" and (not oneOffTaskNetsId or not oneOffTaskSgsId):
        print("Error: for launch type 'FARGATE' the network configuration must be provided using the `--networks-id` and `--security-groups-id` flags.")
        sys.exit(1)

    # Get the latest active task definition from refTaskDefName
    latestActiveTaskDef = ecs.describe_task_definition(
        taskDefinition=refTaskDefName
    )

    # Remove unnecessary keys from the task definition
    # See https://github.com/aws/aws-cli/issues/3064#issuecomment-504681953
    del latestActiveTaskDef['taskDefinition']['taskDefinitionArn']
    del latestActiveTaskDef['taskDefinition']['revision']
    del latestActiveTaskDef['taskDefinition']['status']
    # This key is only present when are required some attributes such as S3 environment files
    try:
        del latestActiveTaskDef['taskDefinition']['requiresAttributes']
    except KeyError:
        pass
    del latestActiveTaskDef['taskDefinition']['compatibilities']
    del latestActiveTaskDef['ResponseMetadata']
    # Added in recent versions of boto3 (1.17.64). For backward compatibility we use exceptions
    try:
        del latestActiveTaskDef['taskDefinition']['registeredAt']
    except KeyError:
        pass
    try:
        del latestActiveTaskDef['taskDefinition']['registeredBy']
    except KeyError:
        pass

    # Get the secrets, environment files and environment variables for the first container
    containerSecrets = latestActiveTaskDef['taskDefinition']['containerDefinitions'][0].get('secrets', None)
    containerEnvFiles = latestActiveTaskDef['taskDefinition']['containerDefinitions'][0].get('environmentFiles', None)
    containerEnv = latestActiveTaskDef['taskDefinition']['containerDefinitions'][0].get('environment', None)
    # Get the execution role ARN for the task
    execRoleArn = latestActiveTaskDef['taskDefinition'].get('executionRoleArn', None)

    if oneOffTaskLaunchType == "EC2":
        # Build the one-off task definition for EC2
        oneOffTaskDef = {
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
    else:
        # Build the one-off task definition for Fargate
        oneOffTaskDef = {
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
            "family": oneOffTaskName,
            "networkMode": "awsvpc",
            "requiresCompatibilities": [
                "FARGATE"
            ],
            "cpu": "256",
            "memory": "512"
        }

    # Update task definition with optionals keys
    if containerEntrypoint:
        oneOffTaskDef['containerDefinitions'][0].update({"entryPoint": containerEntrypoint.split(' ')})

    if containerEnvFiles:
        oneOffTaskDef['containerDefinitions'][0].update({"environmentFiles": containerEnvFiles})

    if containerSecrets:
        oneOffTaskDef['containerDefinitions'][0].update({"secrets": containerSecrets})

    if containerEnvFiles:
        oneOffTaskDef['containerDefinitions'][0].update({"environment": containerEnv})

    # Create a new task revision for the one-off task
    response = ecs.register_task_definition(**oneOffTaskDef)

    # Get the one-off task definition ARN
    oneOffTaskDefArn = response['taskDefinition']['taskDefinitionArn']

    print(f"==> Created the task definition: {oneOffTaskDefArn}")

    # Create the one-off task container CloudWatch Log Group if does not exists
    print("\n" + createCloudWatchLogGroup(logGroupName=oneOffTaskContainerLogGroup))

    # Run the one-off task with the created task definition (oneOffTaskDefArn)
    if oneOffTaskLaunchType == "EC2":
        response = ecs.run_task(
            cluster=ecsCluster,
            taskDefinition=oneOffTaskDefArn
        )
    else:
        response = ecs.run_task(
            cluster=ecsCluster,
            taskDefinition=oneOffTaskDefArn,
            launchType='FARGATE',
            networkConfiguration={
                'awsvpcConfiguration': {
                    'subnets': oneOffTaskNetsId,
                    'securityGroups': oneOffTaskSgsId,
                    'assignPublicIp': 'DISABLED'
                }
            }
        )

    # Get the one-off run task ARN
    oneOffTaskRunArn = response['tasks'][0]['taskArn']

    print(f"\n==> Executed task ARN: {oneOffTaskRunArn}")
    print("\nWaiting for the task to finishes...")

    # Wait until the one-off task is stopped
    # The poll is every 6 seconds by default and the maximun number of attempts to be made is 100
    waiter = ecs.get_waiter('tasks_stopped')
    waiter.wait(
        cluster=ecsCluster,
        tasks=[
            oneOffTaskRunArn
        ]
    )

    # Get the output of the stopped task
    response = ecs.describe_tasks(
        cluster=ecsCluster,
        tasks=[
            oneOffTaskRunArn
        ]
    )

    # Get the container exit status code and its reason
    oneOffTaskExitCode = response['tasks'][0]['containers'][0].get('exitCode')
    oneOffTaskExitCodeReason = response['tasks'][0]['containers'][0].get('reason')

    # Get the one-off task stopped reason
    oneOffTaskStopeedReason = response['tasks'][0].get('stoppedReason')

    if oneOffTaskExitCode == 0 and not oneOffTaskExitCode:
        print("\n==> The one-off task process has finished correctly!!")
        printContainerOutput(logGroupName=oneOffTaskContainerLogGroup, taskArn=oneOffTaskRunArn)
        sys.exit()
    else:
        print("\n==> The one-off task has failed!!")
        print(f"Container exit code: {oneOffTaskExitCode}")
        print(f"Container exit reason: {oneOffTaskExitCodeReason}")
        print(f"Stopped reason: {oneOffTaskStopeedReason}")
        printContainerOutput(logGroupName=oneOffTaskContainerLogGroup, taskArn=oneOffTaskRunArn)
        sys.exit(1)


def getOptions(args=sys.argv[1:]):
    """ Parse the script options.

        Args:
            args: the script options.
    """

    # Create the top-level parser
    parser = argparse.ArgumentParser(prog=sys.argv[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Creates a one-off ECS task from a task definition already created",
        epilog=textwrap.dedent(f'''\
            Usage samples:
            --------------
                Run a one-off task on EC2 instances:
                    {sys.argv[0]} --task-name <TASK_NAME> --from-task <REFERENCE_TASK_NAME> --cluster <ECS_CLUSTER_NAME> \\
                        --image <OCI_IMAGE> --entrypoint <ENTRYPOINT> --command <COMMAND>

                Run a one-off task on Fargate:
                    {sys.argv[0]} --task-name <TASK_NAME> --from-task <REFERENCE_TASK_NAME> --cluster <ECS_CLUSTER_NAME> \\
                        --image <OCI_IMAGE> --entrypoint <ENTRYPOINT> --command <COMMAND> \\
                        --launch-type FARGATE --networks-id  <NET_ID1 NET_ID2 ...> --security-groups-id <SG_ID1 SG_ID2...>
            ''')
    )

    # Global options
    parser.add_argument("-p", "--profile", help="a valid AWS profile name to perform the tasks")
    parser.add_argument("-r", "--region", help="a valid AWS region to perform the tasks")
    parser.add_argument("--task-name", required=True, help="the name for one-off task")
    parser.add_argument("--from-task", required=True, help="the name of the reference task to create the one-off task")
    parser.add_argument("--cluster", required=True, help="the ECS cluster name to connect")
    parser.add_argument("--image", required=True, help="the image URI for the one-off task")
    parser.add_argument("--entrypoint", help="the entrypoint for the one-off task, e.g.: 'sh -c'")
    parser.add_argument("--command", required=True, nargs='+', help="the command for the one-off task")
    parser.add_argument("--launch-type", default='EC2', choices=["EC2", "FARGATE"], help="the launch type on which to run the one-off task")
    parser.add_argument(
        "--networks-id",
        nargs='*',
        help="the IDs of the subnets associated with the one-off task. All specified subnets must be from the same VPC"
    )
    parser.add_argument(
        "--security-groups-id",
        nargs='*',
        help="the IDs of the security groups associated with the one-off task. All specified security groups must be from the same VPC."
    )

    # Print usage and exit if not arguments are supplied
    if not args:
        parser.print_help(sys.stderr)
        sys.exit(1)

    # Parse the args
    options = parser.parse_args(args)

    # Return the parsed args
    return options


def main():
    """ Main function.

        Args:
          None.
    """
    # Parse the args
    options = getOptions(sys.argv[1:])

    # Initialize the AWS clients
    initializeAwsClients(options)

    # Select the script actions
    createRunTaskDefinition(options)


if __name__ == "__main__":
    main()
