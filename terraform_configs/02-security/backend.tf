terraform {
  backend "s3" {
    bucket = "my-eks-cluster-terraform-state"
    key    = "security/terraform.tfstate"
    region = "eu-north-1"
  }
}
