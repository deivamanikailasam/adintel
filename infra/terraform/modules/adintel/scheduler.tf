# EventBridge Scheduler: one schedule per brand in its own timezone (created by the brand-onboarding job
# through the API, not by Terraform), all in this group. The group is the unit for the global pause.
resource "aws_scheduler_schedule_group" "brands" {
  name = "adintel-${var.env}-brands"
}

data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "eventbridge" {
  name               = "adintel-${var.env}-eventbridge"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

resource "aws_iam_role_policy" "eventbridge" {
  role = aws_iam_role.eventbridge.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
  Effect = "Allow", Action = ["sqs:SendMessage"], Resource = [aws_sqs_queue.agent_runs.arn] }] })
}
