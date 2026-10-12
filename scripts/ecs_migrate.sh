#!/usr/bin/env bash
# Run `adintel migrate` as a one-off ECS task with the scheduler's task definition (same image, same
# network, same database role) and fail the pipeline if it does not exit 0.
#
#   scripts/ecs_migrate.sh <cluster> <task-definition-family> <subnet-ids,comma> <security-group-id> <owner>
set -euo pipefail
CLUSTER=$1 FAMILY=$2 SUBNETS=$3 SG=$4 OWNER=$5
OVERRIDES=$(printf '{"containerOverrides":[{"name":"scheduler","command":["adintel","migrate","--owner","%s"]}]}' "$OWNER")
TASK=$(aws ecs run-task --cluster "$CLUSTER" --task-definition "$FAMILY" --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SG],assignPublicIp=DISABLED}" \
  --overrides "$OVERRIDES" --query 'tasks[0].taskArn' --output text)
echo "migration task: $TASK"
aws ecs wait tasks-stopped --cluster "$CLUSTER" --tasks "$TASK"
CODE=$(aws ecs describe-tasks --cluster "$CLUSTER" --tasks "$TASK" --query 'tasks[0].containers[0].exitCode' --output text)
echo "exit code: $CODE"
[ "$CODE" = "0" ]
