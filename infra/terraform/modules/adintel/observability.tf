resource "aws_sns_topic" "alerts" {
  for_each          = toset(["p1", "p2", "p3"])
  name              = "adintel-${var.env}-${each.key}"
  kms_master_key_id = aws_kms_key.this.id
}

resource "aws_sns_topic_subscription" "email" {
  count     = var.alarm_email == "" ? 0 : 1
  topic_arn = aws_sns_topic.alerts["p1"].arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

# DLQ depth > 0 → P2 (both queues).
resource "aws_cloudwatch_metric_alarm" "dlq" {
  for_each            = { runs = aws_sqs_queue.agent_runs_dlq.name, executions = aws_sqs_queue.executions_dlq.name }
  alarm_name          = "adintel-${var.env}-dlq-${each.key}"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = each.value }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  alarm_actions       = [aws_sns_topic.alerts["p2"].arn]
}

# Application metrics are emitted as EMF into namespace AdIntel; the P1 security alarms:
resource "aws_cloudwatch_metric_alarm" "tenant_violation" {
  alarm_name          = "adintel-${var.env}-tenant-isolation-violation"
  namespace           = "AdIntel"
  metric_name         = "adintel_tenant_isolation_violations_total"
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts["p1"].arn]
}

resource "aws_cloudwatch_metric_alarm" "reconciliation" {
  alarm_name          = "adintel-${var.env}-execution-mismatch"
  namespace           = "AdIntel"
  metric_name         = "adintel_execution_reconciliation_mismatches_total"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts["p1"].arn]
}

resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  alarm_name          = "adintel-${var.env}-alb-5xx"
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HTTPCode_Target_5XX_Count"
  dimensions          = { LoadBalancer = aws_lb.api.arn_suffix }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 2
  threshold           = 25
  comparison_operator = "GreaterThanThreshold"
  alarm_actions       = [aws_sns_topic.alerts["p2"].arn]
}
