output "alb_url"           { value = "http://${aws_lb.main.dns_name}" }
output "cloudfront_url"    { value = "https://${aws_cloudfront_distribution.frontend.domain_name}" }
output "documents_bucket"  { value = aws_s3_bucket.documents.id }
output "frontend_bucket"   { value = aws_s3_bucket.frontend.id }
output "ecr_repo_url"      { value = aws_ecr_repository.backend.repository_url }
output "ddb_table"         { value = aws_dynamodb_table.applications.name }
output "cloudfront_id"     { value = aws_cloudfront_distribution.frontend.id }
output "sns_topic_arn"     { value = aws_sns_topic.notifications.arn }
