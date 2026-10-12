output "api_alb_dns" { value = aws_lb.api.dns_name }
output "agent_runs_queue_url" { value = aws_sqs_queue.agent_runs.url }
output "executions_queue_url" { value = aws_sqs_queue.executions.url }
output "nat_egress_ips" {
  value       = aws_eip.nat[*].public_ip
  description = "Give these to ad platforms that require IP allow-listing"
}
output "cognito_user_pool_id" { value = aws_cognito_user_pool.this.id }
