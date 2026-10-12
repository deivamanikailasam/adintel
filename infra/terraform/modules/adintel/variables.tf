variable "env" {
  type        = string
  description = "staging | prod"
}
variable "region" {
  type    = string
  default = "us-east-1"
}
variable "image" {
  type        = string
  description = "SHA-tagged ECR image (never :latest)"
  validation {
    condition     = !endswith(var.image, ":latest")
    error_message = "Floating :latest tags are not allowed; deploy an immutable SHA tag."
  }
}
variable "vpc_cidr" {
  type    = string
  default = "10.40.0.0/16"
}
variable "azs" {
  type    = list(string)
  default = ["us-east-1a", "us-east-1b", "us-east-1c"]
}
variable "frontier_model_id" {
  type        = string
  description = "Exact, versioned Bedrock model ID for the frontier tier"
}
variable "small_model_endpoint" {
  type        = string
  description = "SageMaker endpoint name for the small tier (OpenAI-compatible LMI container)"
}
variable "report_model_endpoint" {
  type = string
}
variable "guardrail_model_endpoint" {
  type = string
}
variable "atlas_private_endpoint_uri" {
  type        = string
  description = "MongoDB Atlas connection string over PrivateLink (no public endpoint)"
  sensitive   = true
}
variable "api_desired" {
  type    = number
  default = 2
}
variable "worker_desired" {
  type    = number
  default = 2
}
variable "alarm_email" {
  type    = string
  default = ""
}
