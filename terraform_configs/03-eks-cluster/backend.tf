terraform {
  backend "s3" {
    bucket = "my-eks-cluster-terraform-state"
    key    = "eks-cluster/terraform.tfstate"
    region = "eu-north-1"
  }
}
