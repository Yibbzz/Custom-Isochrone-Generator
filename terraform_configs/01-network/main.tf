resource "aws_vpc" "main" {
  cidr_block           = var.vpc_block
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "${var.cluster_name}-VPC"
  }
}

resource "aws_internet_gateway" "gw" {
  vpc_id = aws_vpc.main.id
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
}

resource "aws_route" "default_route" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.gw.id
}

resource "aws_subnet" "subnet01" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.subnet01_block
  availability_zone       = "eu-north-1a"
  map_public_ip_on_launch = true

  tags = {
    "Name" = "${var.cluster_name}-subnet01"
    "kubernetes.io/role/elb" = "1"  # Tag required for the AWS Load Balancer Controller
  }
}

resource "aws_subnet" "subnet02" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.subnet02_block
  availability_zone       = "eu-north-1b"
  map_public_ip_on_launch = true

  tags = {
    "Name" = "${var.cluster_name}-subnet02"
    "kubernetes.io/role/elb" = "1"  # Tag required for the AWS Load Balancer Controller
  }
}

resource "aws_subnet" "subnet03" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.subnet03_block
  availability_zone       = "eu-north-1c"
  map_public_ip_on_launch = true

  tags = {
    "Name" = "${var.cluster_name}-subnet03"
    "kubernetes.io/role/elb" = "1"  # Tag required for the AWS Load Balancer Controller
  }
}

resource "aws_route_table_association" "subnet01" {
  subnet_id      = aws_subnet.subnet01.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "subnet02" {
  subnet_id      = aws_subnet.subnet02.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "subnet03" {
  subnet_id      = aws_subnet.subnet03.id
  route_table_id = aws_route_table.public.id
}

resource "aws_db_subnet_group" "db_subnet_group" {
  name       = "my-db-subnet-group"
  subnet_ids = [aws_subnet.subnet01.id, aws_subnet.subnet02.id, aws_subnet.subnet03.id]

  tags = {
    Name = "MyDBSubnetGroup"
  }
}
