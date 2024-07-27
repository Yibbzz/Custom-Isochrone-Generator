terraform {
  backend "s3" {
    bucket = "my-eks-cluster-terraform-state"
    key    = "efs-csi/terraform.tfstate"
    region = "eu-north-1"
  }
}
