data "terraform_remote_state" "network" {
  backend = "s3"
  config = {
    bucket = "my-eks-cluster-terraform-state"
    key    = "network/terraform.tfstate"
    region = "eu-north-1"
  }
}

resource "aws_iam_role" "eks_cluster_role" {
  name               = "${var.cluster_name}-eks-cluster-role"
  assume_role_policy = data.aws_iam_policy_document.eks_cluster_assume_role_policy.json

  managed_policy_arns = [
    "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy",
    "arn:aws:iam::aws:policy/AmazonEKSServicePolicy"
  ]
}

data "aws_iam_policy_document" "eks_cluster_assume_role_policy" {
  statement {
    actions = ["sts:AssumeRole"]
    effect  = "Allow"
    principals {
      type        = "Service"
      identifiers = ["eks.amazonaws.com"]
    }
  }
}

resource "aws_security_group" "eks" {
  name_prefix = "${var.cluster_name}-eks"
  description = "Cluster communication with worker nodes"
  vpc_id      = data.terraform_remote_state.network.outputs.vpc_id

  # Allow inbound traffic on port 9443 for AWS Load Balancer webhook
  ingress {
    description = "Allow inbound traffic on port 9443 for AWS Load Balancer webhook"
    from_port   = 9443
    to_port     = 9443
    protocol    = "tcp"
    cidr_blocks = [data.terraform_remote_state.network.outputs.vpc_cidr_block]
  }

  # Allow all outbound traffic
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "eks_nodes" {
  name        = "${var.cluster_name}-eks-nodes"
  description = "Security group for all nodes in the cluster"
  vpc_id      = data.terraform_remote_state.network.outputs.vpc_id

  # Allow inbound traffic from other nodes
  ingress {
    description      = "Allow inbound traffic on port 443 from other nodes"
    from_port        = 443
    to_port          = 443
    protocol         = "tcp"
    self             = true
  }

  # Allow outbound internet access
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}



resource "aws_iam_role" "node_role" {
  name               = "${var.cluster_name}-eks-node-role"
  assume_role_policy = data.aws_iam_policy_document.eks_node_assume_role_policy.json

  managed_policy_arns = [
    "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy",
    "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy",
    "arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy",
    "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly",
    "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
  ]
}

data "aws_iam_policy_document" "eks_node_assume_role_policy" {
  statement {
    actions = ["sts:AssumeRole"]
    effect  = "Allow"
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_security_group" "efs_sg" {
  name        = "efs-sg"
  description = "Security group for EFS"
  vpc_id      = data.terraform_remote_state.network.outputs.vpc_id

  ingress {
    from_port   = 2049
    to_port     = 2049
    protocol    = "tcp"
    cidr_blocks = [data.terraform_remote_state.network.outputs.vpc_cidr_block]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "EFS Security Group"
  }
}


resource "aws_security_group" "rds_sg" {
  name_prefix   = "rds-eks-sg"
  description   = "Security group attached to database-1 to allow EKS worker nodes to connect to the database. Modification could lead to connection loss."
  vpc_id        = data.terraform_remote_state.network.outputs.vpc_id

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [data.terraform_remote_state.network.outputs.vpc_cidr_block]
  }

  tags = {
    Name = "RDSEKSSecurityGroup"
  }
}

resource "random_password" "rds_password" {
  length  = 16
  special = true
  override_special = "!#$%&()*+,-.:;<=>?[]^_{|}~"  # Exclude '@', '/', '"', and ' '
}

resource "aws_secretsmanager_secret" "rds_secret" {
  name        = "my-rds-secret"
  description = "Secret for RDS database credentials"
}

resource "aws_secretsmanager_secret_version" "rds_secret_version" {
  secret_id     = aws_secretsmanager_secret.rds_secret.id
  secret_string = jsonencode({
    username = "nathan",
    password = random_password.rds_password.result
  })
}

