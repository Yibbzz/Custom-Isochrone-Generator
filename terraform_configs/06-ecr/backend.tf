terraform {
  backend "s3" {
    bucket = "my-eks-cluster-terraform-state"
    key    = "ecr/terraform.tfstate"
    region = "eu-north-1"
  }
}
