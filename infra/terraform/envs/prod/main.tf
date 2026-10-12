# prod environment. State in the shared-services account (S3 + DynamoDB lock); one AWS account per
# environment, because an account is the only truly hard blast-radius boundary in AWS.
terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.70" }
  }
  # backend "s3" {
  #   bucket         = "adintel-tfstate-shared"
  #   key            = "prod/adintel.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "adintel-tflock"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = "us-east-1"
  default_tags {
    tags = { Project = "adintel", Environment = "prod", ManagedBy = "terraform" }
  }
}

variable "image" {
  type    = string
  default = "000000000000.dkr.ecr.us-east-1.amazonaws.com/adintel:0000000"
}
variable "atlas_private_endpoint_uri" {
  type      = string
  sensitive = true
  default   = "mongodb+srv://placeholder"
}

module "adintel" {
  source                     = "../../modules/adintel"
  env                        = "prod"
  image                      = var.image
  frontier_model_id          = "anthropic.claude-sonnet-4-5-20250929-v1:0" # exact, versioned ID — pin per eval run
  small_model_endpoint       = "adintel-prod-small"
  report_model_endpoint      = "adintel-prod-report"
  guardrail_model_endpoint   = "adintel-prod-guardrail"
  atlas_private_endpoint_uri = var.atlas_private_endpoint_uri
  vpc_cidr                   = "prod" == "prod" ? "10.40.0.0/16" : "10.41.0.0/16"
  api_desired                = "prod" == "prod" ? 2 : 1
  worker_desired             = "prod" == "prod" ? 2 : 1
}

output "api_alb_dns" { value = module.adintel.api_alb_dns }
output "nat_egress_ips" { value = module.adintel.nat_egress_ips }
