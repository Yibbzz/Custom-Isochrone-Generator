output "eks_cluster_role_arn" {
  value = aws_iam_role.eks_cluster_role.arn
}

output "node_role_arn" {
  value = aws_iam_role.node_role.arn
}

output "eks_security_group_id" {
  value = aws_security_group.eks.id
}

output "eks_nodes_security_group_id" {
  value = aws_security_group.eks_nodes.id
}

output "efs_sg_id" {
  value = aws_security_group.efs_sg.id
}

output "rds_sg_id" {
  value = aws_security_group.rds_sg.id
}

output "db_username" {
  value     = jsondecode(aws_secretsmanager_secret_version.rds_secret_version.secret_string)["username"]
  sensitive = true
}

output "db_password" {
  value     = jsondecode(aws_secretsmanager_secret_version.rds_secret_version.secret_string)["password"]
  sensitive = true
}
