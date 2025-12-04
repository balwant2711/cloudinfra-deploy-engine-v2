variable "aws_region" {
  description = "AWS region"
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
}

variable "public_subnet_1_cidr" {
  description = "CIDR for first public subnet"
  type        = string
}

variable "public_subnet_2_cidr" {
  description = "CIDR for second public subnet"
  type        = string
}

variable "private_subnet_1_cidr" {
  description = "CIDR for first private subnet"
  type        = string
}

variable "private_subnet_2_cidr" {
  description = "CIDR for second private subnet"
  type        = string
}

variable "name_prefix" {
  description = "Prefix for tagging resources"
  type        = string
  default     = "cloudinfra-vpc"
}
