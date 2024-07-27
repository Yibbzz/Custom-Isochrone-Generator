output "efs_id" {
  value = aws_efs_file_system.efs.id
}

output "db_endpoint" {
  value       = aws_db_instance.db_instance.endpoint
  description = "The endpoint of the RDS instance"
}
