# Angular app on S3 + CloudFront; API behind WAF + ALB; identity via Cognito (JWT).
resource "aws_security_group" "alb" {
  name   = "adintel-${var.env}-alb"
  vpc_id = aws_vpc.this.id
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [var.vpc_cidr]
  }
}

resource "aws_lb" "api" {
  name                       = "adintel-${var.env}"
  load_balancer_type         = "application"
  subnets                    = aws_subnet.public[*].id
  security_groups            = [aws_security_group.alb.id]
  idle_timeout               = 900 # long-lived SSE connections
  drop_invalid_header_fields = true
}

resource "aws_lb_target_group" "api" {
  name        = "adintel-${var.env}-api"
  port        = 8000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = aws_vpc.this.id
  health_check {
    path    = "/ready"
    matcher = "200"
  }
}

resource "aws_wafv2_web_acl" "api" {
  name  = "adintel-${var.env}"
  scope = "REGIONAL"
  default_action {
    allow {}
  }
  rule {
    name     = "aws-common"
    priority = 1
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesCommonRuleSet"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "common"
      sampled_requests_enabled   = true
    }
  }
  rule {
    name     = "rate-limit"
    priority = 2
    action {
      block {}
    }
    statement {
      rate_based_statement {
        limit              = 2000
        aggregate_key_type = "IP"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "rate"
      sampled_requests_enabled   = true
    }
  }
  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "adintel"
    sampled_requests_enabled   = true
  }
}

resource "aws_wafv2_web_acl_association" "api" {
  resource_arn = aws_lb.api.arn
  web_acl_arn  = aws_wafv2_web_acl.api.arn
}

resource "aws_s3_bucket" "frontend" {
  bucket = "adintel-${var.env}-frontend"
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket                  = aws_s3_bucket.frontend.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_cognito_user_pool" "this" {
  name                     = "adintel-${var.env}"
  mfa_configuration        = "ON"
  auto_verified_attributes = ["email"]
  software_token_mfa_configuration {
    enabled = true
  }
  password_policy {
    minimum_length    = 14
    require_symbols   = true
    require_numbers   = true
    require_uppercase = true
    require_lowercase = true
  }
  schema {
    name                = "tenant_id"
    attribute_data_type = "String"
    mutable             = false
  }
}
