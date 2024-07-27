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


data "aws_eks_cluster_auth" "cluster" {
  name = data.terraform_remote_state.eks.outputs.cluster_name
}

provider "helm" {
  kubernetes {
    host                   = data.terraform_remote_state.eks.outputs.cluster_endpoint
    token                  = data.aws_eks_cluster_auth.cluster.token
    cluster_ca_certificate = base64decode(data.terraform_remote_state.eks.outputs.cluster_ca_certificate)
  }
}

data "aws_caller_identity" "current" {}

# Create IAM Policy
resource "aws_iam_policy" "load_balancer_controller" {
  name   = "AWSLoadBalancerControllerIAMPolicy"
  policy = file("${path.module}/iam_loadapp_policy.json")
}


resource "aws_iam_role" "load_balancer_controller" {
  name = "AmazonEKSLoadBalancerControllerRole"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Principal = {
          Federated = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/${replace(data.terraform_remote_state.eks.outputs.cluster_oidc_issuer_url, "https://", "")}"
        },
        Action = "sts:AssumeRoleWithWebIdentity",
        Condition = {
          StringEquals = {
            "${replace(data.terraform_remote_state.eks.outputs.cluster_oidc_issuer_url, "https://", "")}:sub": "system:serviceaccount:kube-system:aws-load-balancer-controller"
          }
        }
      }
    ]
  })
}

# Attach the policy to the role
resource "aws_iam_role_policy_attachment" "load_balancer_controller_attach" {
  role       = aws_iam_role.load_balancer_controller.name
  policy_arn = aws_iam_policy.load_balancer_controller.arn
}

resource "kubernetes_service_account" "aws_load_balancer_controller" {
  metadata {
    name      = "aws-load-balancer-controller"
    namespace = "kube-system"

    annotations = {
      "eks.amazonaws.com/role-arn" = aws_iam_role.load_balancer_controller.arn
    }
  }
}

# Fetch the current AWS region dynamically
data "aws_region" "current" {}

# Add the Helm repository and install the chart
resource "helm_release" "aws_load_balancer_controller" {
  name       = "aws-load-balancer-controller"
  repository = "https://aws.github.io/eks-charts"
  chart      = "aws-load-balancer-controller"
  namespace  = "kube-system"

  set {
    name  = "clusterName"
    value = data.terraform_remote_state.eks.outputs.cluster_name
  }

  set {
    name  = "serviceAccount.create"
    value = "false"
  }

  set {
    name  = "serviceAccount.name"
    value = "aws-load-balancer-controller"
  }

  # Use the dynamically fetched region
  set {
    name  = "region"
    value = data.aws_region.current.name
  }

  # Use VPC ID from remote state
  set {
    name  = "vpcId"
    value = data.terraform_remote_state.network.outputs.vpc_id
  }
}

resource "kubernetes_service" "my_django_service" {
  metadata {
    name = "my-django-service"
  }
  spec {
    type = "ClusterIP"
    selector = {
      app = "my-django-app"
    }
    port {
      protocol    = "TCP"
      port        = 80
      target_port = 8000
    }
  }
}


resource "kubernetes_ingress_v1" "django_ingress" {
  depends_on = [helm_release.aws_load_balancer_controller]  # Ensure the ALB controller is deployed first

  metadata {
    name        = "django-ingress"
    annotations = {
      "kubernetes.io/ingress.class"               = "alb"
      "alb.ingress.kubernetes.io/scheme"          = "internet-facing"
      "alb.ingress.kubernetes.io/target-type"     = "ip"
      "alb.ingress.kubernetes.io/certificate-arn" = var.certificate_arn
      "alb.ingress.kubernetes.io/listen-ports"    = "[{\"HTTP\": 80}, {\"HTTPS\":443}]"
      "alb.ingress.kubernetes.io/actions.ssl-redirect" = "{\"Type\": \"redirect\", \"RedirectConfig\": {\"Protocol\": \"HTTPS\", \"Port\": \"443\", \"StatusCode\": \"HTTP_301\"}}"
    }
  }
  spec {
    rule {
      http {
        path {
          path = "/*"
          path_type = "ImplementationSpecific"
          backend {
            service {
              name = "my-django-service"
              port {
                number = 80
              }
            }
          }
        }
      }
    }
  }
}