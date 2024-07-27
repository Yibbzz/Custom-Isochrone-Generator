variable "cluster_name" {
  default = "my-eks-cluster-2"
}

variable "vpc_block" {
  default = "192.168.0.0/16"
}

variable "subnet01_block" {
  default = "192.168.64.0/18"
}

variable "subnet02_block" {
  default = "192.168.128.0/18"
}

variable "subnet03_block" {
  default = "192.168.192.0/18"
}
