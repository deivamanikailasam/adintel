resource "aws_ecs_cluster" "this" {
  name = "adintel-${var.env}"
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_security_group" "app" {
  name   = "adintel-${var.env}-app"
  vpc_id = aws_vpc.this.id
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group_rule" "alb_to_api" {
  type                     = "ingress"
  from_port                = 8000
  to_port                  = 8000
  protocol                 = "tcp"
  security_group_id        = aws_security_group.app.id
  source_security_group_id = aws_security_group.alb.id
}

resource "aws_cloudwatch_log_group" "svc" {
  for_each          = toset(["api", "worker", "executor", "scheduler"])
  name              = "/adintel/${var.env}/${each.key}"
  retention_in_days = 90
  kms_key_id        = aws_kms_key.this.arn
}

locals {
  common_env = [
    { name = "ADINTEL_ENV", value = var.env == "prod" ? "production" : "staging" },
    { name = "ADINTEL_STORAGE", value = "mongo" },
    { name = "ADINTEL_QUEUE", value = "sqs" },
    { name = "ADINTEL_SECRETS", value = "aws" },
    { name = "ADINTEL_LLM_PROVIDER", value = "bedrock" },
    { name = "ADINTEL_CONNECTORS", value = "live" },
    { name = "ADINTEL_DEV_LOGIN_ENABLED", value = "false" },
    { name = "ADINTEL_EMBEDDER", value = "fastembed" },
    { name = "ADINTEL_RERANKER", value = "fastembed" },
    { name = "ADINTEL_SANDBOX", value = "docker" },
  ]
  services = {
    api       = { cpu = 1024, memory = 2048, command = ["uvicorn", "adintel.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"], port = 8000, desired = var.api_desired }
    worker    = { cpu = 2048, memory = 8192, command = ["python", "-m", "adintel.workers.agent_worker"], port = null, desired = var.worker_desired }
    executor  = { cpu = 512, memory = 1024, command = ["python", "-m", "adintel.executor"], port = null, desired = 1 }
    scheduler = { cpu = 256, memory = 512, command = ["python", "-m", "adintel.scheduler"], port = null, desired = 1 }
  }
}

resource "aws_ecs_task_definition" "svc" {
  for_each                 = local.services
  family                   = "adintel-${var.env}-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = each.value.cpu
  memory                   = each.value.memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task[each.key].arn
  container_definitions = jsonencode([{
    name         = each.key
    image        = var.image
    command      = each.value.command
    essential    = true
    stopTimeout  = 120
    portMappings = each.value.port == null ? [] : [{ containerPort = each.value.port, protocol = "tcp" }]
    environment  = concat(local.common_env, [{ name = "ADINTEL_PROCESS_ROLE", value = each.key }])
    secrets = [
      { name = "ADINTEL_MONGO_URI", valueFrom = aws_secretsmanager_secret.atlas_uri.arn },
    ]
    readonlyRootFilesystem = each.key == "executor"
    logConfiguration = {
      logDriver = "awslogs"
      options = { "awslogs-group" = aws_cloudwatch_log_group.svc[each.key].name, "awslogs-region" = var.region,
      "awslogs-stream-prefix" = each.key }
    }
  }])
}

resource "aws_ecs_service" "svc" {
  for_each        = local.services
  name            = "adintel-${each.key}"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.svc[each.key].arn
  desired_count   = each.value.desired
  launch_type     = "FARGATE"
  network_configuration {
    subnets         = aws_subnet.app[*].id
    security_groups = [aws_security_group.app.id]
  }
  dynamic "load_balancer" {
    for_each = each.key == "api" ? [1] : []
    content {
      target_group_arn = aws_lb_target_group.api.arn
      container_name   = "api"
      container_port   = 8000
    }
  }
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
}

# Workers scale 2–40 on queue depth (runs take 30–300 s); the API 2–20 on CPU.
resource "aws_appautoscaling_target" "worker" {
  service_namespace  = "ecs"
  resource_id        = "service/${aws_ecs_cluster.this.name}/${aws_ecs_service.svc["worker"].name}"
  scalable_dimension = "ecs:service:DesiredCount"
  min_capacity       = 2
  max_capacity       = 40
}

resource "aws_appautoscaling_policy" "worker_queue" {
  name               = "queue-depth"
  service_namespace  = aws_appautoscaling_target.worker.service_namespace
  resource_id        = aws_appautoscaling_target.worker.resource_id
  scalable_dimension = aws_appautoscaling_target.worker.scalable_dimension
  policy_type        = "TargetTrackingScaling"
  target_tracking_scaling_policy_configuration {
    target_value = 2
    customized_metric_specification {
      metric_name = "ApproximateNumberOfMessagesVisible"
      namespace   = "AWS/SQS"
      statistic   = "Average"
      dimensions {
        name  = "QueueName"
        value = aws_sqs_queue.agent_runs.name
      }
    }
  }
}

resource "aws_appautoscaling_target" "api" {
  service_namespace  = "ecs"
  resource_id        = "service/${aws_ecs_cluster.this.name}/${aws_ecs_service.svc["api"].name}"
  scalable_dimension = "ecs:service:DesiredCount"
  min_capacity       = 2
  max_capacity       = 20
}

resource "aws_appautoscaling_policy" "api_cpu" {
  name               = "cpu"
  service_namespace  = aws_appautoscaling_target.api.service_namespace
  resource_id        = aws_appautoscaling_target.api.resource_id
  scalable_dimension = aws_appautoscaling_target.api.scalable_dimension
  policy_type        = "TargetTrackingScaling"
  target_tracking_scaling_policy_configuration {
    target_value = 60
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
  }
}
