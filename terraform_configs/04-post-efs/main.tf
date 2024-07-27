data "terraform_remote_state" "security" {
  backend = "s3"
  config = {
    bucket = "my-eks-cluster-terraform-state"
    key    = "security/terraform.tfstate"
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

data "terraform_remote_state" "network" {
  backend = "s3"
  config = {
    bucket = "my-eks-cluster-terraform-state"
    key    = "network/terraform.tfstate"
    region = "eu-north-1"
  }
}

resource "aws_db_instance" "db_instance" {
  identifier              = "database-1"
  instance_class          = "db.t3.micro"
  engine                  = "postgres"
  db_name                 = "postgresdb"
  allocated_storage       = 20
  username                = data.terraform_remote_state.security.outputs.db_username
  password                = data.terraform_remote_state.security.outputs.db_password
  vpc_security_group_ids = [data.terraform_remote_state.security.outputs.rds_sg_id]
  db_subnet_group_name    = data.terraform_remote_state.network.outputs.db_subnet_group_name
  skip_final_snapshot     = true
}

# EFS Filesystems and mount targets
resource "aws_efs_file_system" "efs" {
  encrypted           = true
  performance_mode    = "generalPurpose"
  throughput_mode     = "bursting"
  lifecycle_policy {
    transition_to_ia = "AFTER_30_DAYS"
  }
}

resource "aws_efs_mount_target" "mount_target1" {
  file_system_id  = aws_efs_file_system.efs.id
  subnet_id       = element(data.terraform_remote_state.network.outputs.subnet_ids, 0)
  security_groups = [data.terraform_remote_state.security.outputs.efs_sg_id]
}

resource "aws_efs_mount_target" "mount_target2" {
  file_system_id  = aws_efs_file_system.efs.id
  subnet_id       = element(data.terraform_remote_state.network.outputs.subnet_ids, 1)
  security_groups = [data.terraform_remote_state.security.outputs.efs_sg_id]
}

resource "aws_efs_mount_target" "mount_target3" {
  file_system_id  = aws_efs_file_system.efs.id
  subnet_id       = element(data.terraform_remote_state.network.outputs.subnet_ids, 2)
  security_groups = [data.terraform_remote_state.security.outputs.efs_sg_id]
}