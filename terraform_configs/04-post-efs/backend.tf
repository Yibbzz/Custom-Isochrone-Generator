terraform {
  backend "s3" {
    bucket = "my-eks-cluster-terraform-state"
    key    = "post-eks/terraform.tfstate"
    region = "eu-north-1"
  }
}
