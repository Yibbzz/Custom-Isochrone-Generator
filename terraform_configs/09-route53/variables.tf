variable "alb_dns_name" {
  description = "The DNS name of the ALB."
  type        = string
}

variable "certificate_validation_name" {
  description = "The DNS name for the certificate validation record."
  type        = string
}

variable "certificate_validation_record" {
  description = "The DNS record value for the certificate validation."
  type        = string
}
