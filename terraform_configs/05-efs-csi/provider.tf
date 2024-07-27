provider "aws" {
  region = "eu-north-1"
}

provider "helm" {
  kubernetes {
    host                   = data.terraform_remote_state.eks-cluster.outputs.cluster_endpoint
    token                  = data.aws_eks_cluster_auth.cluster.token
    cluster_ca_certificate = base64decode(data.terraform_remote_state.eks-cluster.outputs.cluster_ca_certificate)
  }
}


provider "kubernetes" {
  host                   = module.eks.cluster_endpoint
  cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)

  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    args = [
      "eks",
      "get-token",
      "--cluster-name",
      module.eks.cluster_name
    ]
  }
}