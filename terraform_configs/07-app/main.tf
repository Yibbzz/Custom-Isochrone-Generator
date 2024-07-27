data "terraform_remote_state" "security" {
  backend = "s3"
  config = {
    bucket = "my-eks-cluster-terraform-state"
    key    = "security/terraform.tfstate"
    region = "eu-north-1"
  }
}

data "terraform_remote_state" "post-eks" {
  backend = "s3"
  config = {
    bucket = "my-eks-cluster-terraform-state"
    key    = "post-eks/terraform.tfstate"
    region = "eu-north-1"
  }
}

data "terraform_remote_state" "network" {
  backend = "s3"
  config = {
    bucket = "my-eks-cluster-terraform-state"
    key    = "network/terraform.tfstate"
    region = "eu-north-1"
  }
}

data "terraform_remote_state" "eks" {
  backend = "s3"
  config = {
    bucket = "my-eks-cluster-terraform-state"
    key    = "eks-cluster/terraform.tfstate"
    region = "eu-north-1"
  }
}

data "terraform_remote_state" "efs-csi" {
  backend = "s3"
  config = {
    bucket = "my-eks-cluster-terraform-state"
    key    = "efs-csi/terraform.tfstate"
    region = "eu-north-1"
  }
}

data "terraform_remote_state" "ecr" {
  backend = "s3"
  config = {
    bucket = "my-eks-cluster-terraform-state"
    key    = "efs-csi/terraform.tfstate"
    region = "eu-north-1"
  }
}

