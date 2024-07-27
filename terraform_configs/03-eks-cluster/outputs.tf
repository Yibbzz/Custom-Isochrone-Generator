output "cluster_id" {
  description = "The identifier of the EKS cluster."
  value       = module.eks.cluster_id
}

output "cluster_security_group_id" {
  description = "The security group ID attached to the EKS cluster."
  value       = module.eks.cluster_security_group_id
}

output "cluster_endpoint" {
  description = "The endpoint for the EKS cluster API server."
  value       = module.eks.cluster_endpoint
}

output "cluster_name" {
  description = "The name of the EKS cluster."
  value       = module.eks.cluster_name  
}

output "cluster_ca_certificate" {
  value = module.eks.cluster_certificate_authority_data
}

output "cluster_oidc_issuer_url" {
  description = "The OIDC issuer URL for the EKS cluster."
  value       = module.eks.cluster_oidc_issuer_url  
}

