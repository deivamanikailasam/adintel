resource "aws_kms_key" "this" {
  description         = "adintel-${var.env} data encryption"
  enable_key_rotation = true
}

# Knowledge-base sources, reports, prompt archives (13 months) and exports. Versioned, encrypted,
# public access blocked, Glacier IR after 90 days.
resource "aws_s3_bucket" "artifacts" {
  bucket = "adintel-${var.env}-artifacts"
}

resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.this.arn
    }
  }
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket                  = aws_s3_bucket.artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  rule {
    id     = "glacier-ir-after-90d"
    status = "Enabled"
    filter {}
    transition {
      days          = 90
      storage_class = "GLACIER_IR"
    }
  }
}

# Daily audit-log export with Object Lock (compliance mode, 7 years): tamper-proof copy of the chain.
resource "aws_s3_bucket" "audit" {
  bucket              = "adintel-${var.env}-audit"
  object_lock_enabled = true
}

resource "aws_s3_bucket_object_lock_configuration" "audit" {
  bucket = aws_s3_bucket.audit.id
  rule {
    default_retention {
      mode  = "COMPLIANCE"
      years = 7
    }
  }
}

# Queues: agent-runs (visibility = run budget 900 s) and executions FIFO (order of writes matters).
resource "aws_sqs_queue" "agent_runs_dlq" {
  name              = "adintel-${var.env}-agent-runs-dlq"
  kms_master_key_id = aws_kms_key.this.id
}

resource "aws_sqs_queue" "agent_runs" {
  name                       = "adintel-${var.env}-agent-runs"
  visibility_timeout_seconds = 900
  kms_master_key_id          = aws_kms_key.this.id
  redrive_policy             = jsonencode({ deadLetterTargetArn = aws_sqs_queue.agent_runs_dlq.arn, maxReceiveCount = 5 })
}

resource "aws_sqs_queue" "executions_dlq" {
  name              = "adintel-${var.env}-executions-dlq.fifo"
  fifo_queue        = true
  kms_master_key_id = aws_kms_key.this.id
}

resource "aws_sqs_queue" "executions" {
  name                        = "adintel-${var.env}-executions.fifo"
  fifo_queue                  = true
  content_based_deduplication = false
  visibility_timeout_seconds  = 120
  kms_master_key_id           = aws_kms_key.this.id
  redrive_policy              = jsonencode({ deadLetterTargetArn = aws_sqs_queue.executions_dlq.arn, maxReceiveCount = 5 })
}

# Application secrets (JWT verification, approval signing). Platform credentials are created per tenant
# under adintel/<tenant>/<platform>/{read,write} by the onboarding runbook, rotated every 90 days.
resource "aws_secretsmanager_secret" "approval_signing_key" {
  name       = "adintel/${var.env}/approval-signing-key"
  kms_key_id = aws_kms_key.this.arn
}

resource "aws_secretsmanager_secret" "atlas_uri" {
  name       = "adintel/${var.env}/atlas-uri"
  kms_key_id = aws_kms_key.this.arn
}

resource "aws_secretsmanager_secret_version" "atlas_uri" {
  secret_id     = aws_secretsmanager_secret.atlas_uri.id
  secret_string = var.atlas_private_endpoint_uri
}

# ElastiCache Redis: semantic cache, rate-limit buckets, SSE reconnect buffers.
resource "aws_elasticache_subnet_group" "this" {
  name       = "adintel-${var.env}"
  subnet_ids = aws_subnet.data[*].id
}

resource "aws_security_group" "redis" {
  name   = "adintel-${var.env}-redis"
  vpc_id = aws_vpc.this.id
  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }
}

resource "aws_elasticache_replication_group" "this" {
  replication_group_id       = "adintel-${var.env}"
  description                = "AdIntel cache"
  engine                     = "redis"
  node_type                  = "cache.t4g.medium"
  num_cache_clusters         = 2
  automatic_failover_enabled = true
  multi_az_enabled           = true
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  kms_key_id                 = aws_kms_key.this.arn
  subnet_group_name          = aws_elasticache_subnet_group.this.name
  security_group_ids         = [aws_security_group.redis.id]
}
