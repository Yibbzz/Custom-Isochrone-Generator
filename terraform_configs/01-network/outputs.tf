output "vpc_id" {
  value = aws_vpc.main.id
}

output "subnet_ids" {
  value = [aws_subnet.subnet01.id, aws_subnet.subnet02.id, aws_subnet.subnet03.id]
}

output "vpc_cidr_block" {
  value = aws_vpc.main.cidr_block
}

output "db_subnet_group_name" {
  value = aws_db_subnet_group.db_subnet_group.name
}
