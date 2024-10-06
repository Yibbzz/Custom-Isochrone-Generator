output "django_app_repository_uri" {
  value = aws_ecr_repository.django_app.repository_url
  description = "ECR Repository URI for Django App"
}

output "graphhopper_repository_uri" {
  value = aws_ecr_repository.graphhopper.repository_url
  description = "ECR Repository URI for Graphhopper"
}

