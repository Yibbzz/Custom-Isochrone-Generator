data "terraform_remote_state" "network" {
  backend = "s3"
  config = {
    bucket = "my-eks-cluster-terraform-state"
    key    = "network/terraform.tfstate"
    region = "eu-north-1"
  }
}

data "terraform_remote_state" "security" {
  backend = "s3"
  config = {
    bucket = "my-eks-cluster-terraform-state"
    key    = "security/terraform.tfstate"
    region = "eu-north-1"
  }
}


# EKS Cluster Configuration
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 19.0"

  cluster_name    = "my-eks-cluster-2"
  cluster_version = "1.30"
  vpc_id          = data.terraform_remote_state.network.outputs.vpc_id
  subnet_ids      = data.terraform_remote_state.network.outputs.subnet_ids

  cluster_endpoint_public_access = true
  create_iam_role                = false
  iam_role_arn                   = aws_iam_role.eks_service_role.arn

  create_cluster_security_group = true

  cluster_additional_security_group_ids = [
      data.terraform_remote_state.security.outputs.eks_security_group_id,
      data.terraform_remote_state.security.outputs.rds_sg_id
  ]

  cluster_addons = {
    coredns    = { most_recent = true }
    kube-proxy = { most_recent = true }
    vpc-cni    = { most_recent = true }
  }

  eks_managed_node_groups = {
    default = {
      min_size     = 1
      max_size     = 1
      desired_size = 1
      instance_types = ["t3.medium"]
      capacity_type  = "SPOT"

      create_node_security_group = true
      iam_role_arn               = aws_iam_role.node_instance_role.arn
      
      node_security_group_additional_rules = [
        {
          description                  = "Allow internal cluster communication on port 9443"
          from_port                    = 9443
          to_port                      = 9443
          protocol                     = "tcp"
          source_cluster_security_group = true
        }
      ]
    }
  }
}


# EKS Service Role
resource "aws_iam_role" "eks_service_role" {
  name = "eks_service_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Principal = {
          Service = "eks.amazonaws.com"
        },
        Action = "sts:AssumeRole"
      }
    ]
  })
}

# Attach AWS managed policies to the EKS Service Role
resource "aws_iam_role_policy_attachment" "eks_cluster_policy" {
  role       = aws_iam_role.eks_service_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}

resource "aws_iam_role_policy_attachment" "eks_service_policy" {
  role       = aws_iam_role.eks_service_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSServicePolicy"
}

# Node Instance Role
resource "aws_iam_role" "node_instance_role" {
  name = "node_instance_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Principal = {
          Service = "ec2.amazonaws.com"
        },
        Action = "sts:AssumeRole"
      }
    ]
  })
}

# Attach AWS managed policies to the Node Instance Role
resource "aws_iam_role_policy_attachment" "node_worker_policy" {
  role       = aws_iam_role.node_instance_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
}

resource "aws_iam_role_policy_attachment" "node_cni_policy" {
  role       = aws_iam_role.node_instance_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
}

resource "aws_iam_role_policy_attachment" "app_runner_policy" {
  role       = aws_iam_role.node_instance_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess"
}

resource "aws_iam_role_policy_attachment" "ecr_read_only_policy" {
  role       = aws_iam_role.node_instance_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

# Define and Attach Custom Policies
resource "aws_iam_policy" "custom_node_policy" {
  name        = "custom_node_policy"
  description = "Custom policy for EKS nodes"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "eks:DescribeCluster",
          "elasticfilesystem:DescribeMountTargets",
          "elasticfilesystem:ClientMount",
          "elasticfilesystem:ClientWrite",
          "ecr:BatchCheckLayerAvailability",
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer",
          "ecr:GetAuthorizationToken"
        ],
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "custom_node_policy_attach" {
  role       = aws_iam_role.node_instance_role.name
  policy_arn = aws_iam_policy.custom_node_policy.arn
} 