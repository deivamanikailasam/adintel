# IAM: the single most important decision. Each service has its own narrow task role.
#   * agent-worker: may invoke models and read data; CANNOT read write-credentials.
#   * executor:     may read write-credentials and its queue; has NO bedrock:InvokeModel / sagemaker:Invoke.
#   * api:          read-only platform credentials (approval-time live check), approval signing key.
# Compromising the worker (e.g. via prompt injection) still doesn't give anyone the ability to spend money.
data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

locals {
  secrets_prefix = "arn:aws:secretsmanager:${var.region}:${data.aws_caller_identity.current.account_id}:secret:adintel"
}

data "aws_caller_identity" "current" {}

resource "aws_iam_role" "task" {
  for_each           = toset(["api", "worker", "executor", "scheduler"])
  name               = "adintel-${var.env}-${each.key}"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

data "aws_iam_policy_document" "worker" {
  statement {
    sid       = "InvokeModels"
    actions   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream", "bedrock:Converse", "bedrock:ConverseStream"]
    resources = ["arn:aws:bedrock:${var.region}::foundation-model/${var.frontier_model_id}"]
  }
  statement {
    sid     = "InvokeSelfHostedModels"
    actions = ["sagemaker:InvokeEndpoint", "sagemaker:InvokeEndpointWithResponseStream"]
    resources = [for e in [var.small_model_endpoint, var.report_model_endpoint, var.guardrail_model_endpoint] :
    "arn:aws:sagemaker:${var.region}:${data.aws_caller_identity.current.account_id}:endpoint/${e}"]
  }
  statement {
    sid       = "ReadOnlyPlatformCredentials"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = ["${local.secrets_prefix}/*/*/read-*", aws_secretsmanager_secret.atlas_uri.arn]
  }
  statement {
    sid       = "RunQueue"
    actions   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:ChangeMessageVisibility", "sqs:GetQueueUrl", "sqs:GetQueueAttributes"]
    resources = [aws_sqs_queue.agent_runs.arn, aws_sqs_queue.agent_runs_dlq.arn]
  }
  statement {
    actions   = ["kms:Decrypt"]
    resources = [aws_kms_key.this.arn]
  }
  statement {
    sid       = "PromptArchive"
    actions   = ["s3:PutObject", "s3:GetObject"]
    resources = ["${aws_s3_bucket.artifacts.arn}/prompt-archive/*", "${aws_s3_bucket.artifacts.arn}/reports/*"]
  }
}

data "aws_iam_policy_document" "executor" {
  statement {
    sid       = "WriteCredentialsOnly"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = ["${local.secrets_prefix}/*/*/write-*", "${local.secrets_prefix}/*/*/read-*", aws_secretsmanager_secret.approval_signing_key.arn, aws_secretsmanager_secret.atlas_uri.arn]
  }
  statement {
    sid       = "ExecutionsQueue"
    actions   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:ChangeMessageVisibility", "sqs:GetQueueUrl", "sqs:GetQueueAttributes"]
    resources = [aws_sqs_queue.executions.arn, aws_sqs_queue.executions_dlq.arn]
  }
  statement {
    actions   = ["kms:Decrypt"]
    resources = [aws_kms_key.this.arn]
  }
  # Belt and braces: an explicit deny on every model API, so no future policy can grant it by accident.
  statement {
    sid       = "NeverInvokeModels"
    effect    = "Deny"
    actions   = ["bedrock:*", "sagemaker:InvokeEndpoint", "sagemaker:InvokeEndpointWithResponseStream"]
    resources = ["*"]
  }
}

data "aws_iam_policy_document" "api" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = ["${local.secrets_prefix}/*/*/read-*", aws_secretsmanager_secret.approval_signing_key.arn, aws_secretsmanager_secret.atlas_uri.arn]
  }
  statement {
    actions   = ["sqs:SendMessage", "sqs:GetQueueUrl", "sqs:GetQueueAttributes"]
    resources = [aws_sqs_queue.agent_runs.arn, aws_sqs_queue.executions.arn]
  }
  statement {
    sid       = "ChatModels"
    actions   = ["bedrock:InvokeModelWithResponseStream", "bedrock:ConverseStream"]
    resources = ["arn:aws:bedrock:${var.region}::foundation-model/${var.frontier_model_id}"]
  }
  statement {
    actions   = ["sagemaker:InvokeEndpoint", "sagemaker:InvokeEndpointWithResponseStream"]
    resources = ["arn:aws:sagemaker:${var.region}:${data.aws_caller_identity.current.account_id}:endpoint/${var.small_model_endpoint}"]
  }
  statement {
    actions   = ["kms:Decrypt"]
    resources = [aws_kms_key.this.arn]
  }
  statement {
    sid       = "NeverWrite"
    effect    = "Deny"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = ["${local.secrets_prefix}/*/*/write-*"]
  }
}

data "aws_iam_policy_document" "scheduler" {
  statement {
    actions   = ["sqs:SendMessage", "sqs:GetQueueUrl", "sqs:GetQueueAttributes"]
    resources = [aws_sqs_queue.agent_runs.arn, aws_sqs_queue.agent_runs_dlq.arn, aws_sqs_queue.executions_dlq.arn]
  }
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.atlas_uri.arn]
  }
}

resource "aws_iam_role_policy" "task" {
  for_each = {
    api       = data.aws_iam_policy_document.api.json
    worker    = data.aws_iam_policy_document.worker.json
    executor  = data.aws_iam_policy_document.executor.json
    scheduler = data.aws_iam_policy_document.scheduler.json
  }
  name   = "adintel-${var.env}-${each.key}"
  role   = aws_iam_role.task[each.key].id
  policy = each.value
}

resource "aws_iam_role" "execution" {
  name               = "adintel-${var.env}-ecs-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}
