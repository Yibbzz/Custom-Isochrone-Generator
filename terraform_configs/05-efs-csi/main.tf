data "terraform_remote_state" "eks-cluster" {
  backend = "s3"
  config = {
    bucket = "my-eks-cluster-terraform-state"
    key    = "eks-cluster/terraform.tfstate"
    region = "eu-north-1"
  }
}

resource "helm_release" "efs_csi" {
  name       = "aws-efs-csi-driver"
  repository = "https://kubernetes-sigs.github.io/aws-efs-csi-driver/"
  chart      = "aws-efs-csi-driver"
  namespace  = "kube-system"

  set {
    name  = "serviceAccount.controller.annotations.eks\\.amazonaws\\.com/role-arn"
    value = aws_iam_role.efs_csi_role.arn
  }
}

resource "aws_iam_policy" "efs_csi_policy" {
  name        = "AmazonEKS_EFS_CSI_Driver_Policy"
  description = "Policy for allowing EKS EFS CSI driver to operate"

  policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "elasticfilesystem:ClientMount",
        "elasticfilesystem:ClientWrite",
        "elasticfilesystem:DescribeFileSystems"
      ],
      "Resource": "*"
    }
  ]
}
EOF
}


data "aws_caller_identity" "current" {}

data "aws_eks_cluster_auth" "cluster" {
  name = data.terraform_remote_state.eks-cluster.outputs.cluster_name  // Using cluster_name instead of cluster_id if necessary
}

resource "aws_iam_role" "efs_csi_role" {
  name = "AmazonEKS_EFS_CSI_DriverRole"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Principal = {
          Federated = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/${data.terraform_remote_state.eks-cluster.outputs.cluster_oidc_issuer_url}"
        },
        Action = "sts:AssumeRoleWithWebIdentity",
        Condition = {
          StringEquals = {
            "${data.terraform_remote_state.eks-cluster.outputs.cluster_oidc_issuer_url}:sub" = "system:serviceaccount:kube-system:efs-csi-controller-sa"
          }
        }
      }
    ]
  })
}
