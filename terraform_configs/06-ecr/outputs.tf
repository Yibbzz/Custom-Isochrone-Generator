output "django_app_repository_uri" {
  value = aws_ecr_repository.django_app.repository_url
  description = "ECR Repository URI for Django App"
}

output "graphhopper_repository_uri" {
  value = aws_ecr_repository.graphhopper.repository_url
  description = "ECR Repository URI for Graphhopper"
}

output "buildspec_s3_uri" {
  value = "s3://${aws_s3_bucket_object.buildspec_file.bucket}/${aws_s3_bucket_object.buildspec_file.key}"
  description = "S3 URI of the buildspec file"
}
