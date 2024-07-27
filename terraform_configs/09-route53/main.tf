provider "kubernetes" {
  host                   = data.terraform_remote_state.eks.outputs.cluster_endpoint
  cluster_ca_certificate = base64decode(data.terraform_remote_state.eks.outputs.cluster_ca_certificate)
  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    args = [
      "eks",
      "get-token",
      "--cluster-name",
      data.terraform_remote_state.eks.outputs.cluster_name
    ]
  }
}

data "terraform_remote_state" "app" {
  backend = "s3"
  config = {
    bucket = "my-eks-cluster-terraform-state"
    key    = "app/terraform.tfstate"
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

variable "domain_name" {
  description = "The domain name for the hosted zone."
  default     = "custom-isochrones.co.uk"
}

resource "aws_route53_zone" "main" {
  name = var.domain_name
}

resource "aws_route53_record" "alb_alias" {
  zone_id = aws_route53_zone.main.zone_id
  name    = var.domain_name
  type    = "A"

  alias {
    name                   = var.alb_dns_name
    zone_id                = "Z23TAZ6LKFMNIO"  # Hosted zone ID for ALB
    evaluate_target_health = true
  }
}

resource "aws_route53_record" "certificate_validation" {
  zone_id = aws_route53_zone.main.zone_id
  name    = var.certificate_validation_name
  type    = "CNAME"
  ttl     = 300
  records = [var.certificate_validation_record]
}
