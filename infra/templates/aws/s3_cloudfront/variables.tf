variable "aws_region" {
  description = "AWS region for S3 bucket"
  type        = string
}

variable "bucket_name" {
  description = "Globally unique S3 bucket name for static site"
  type        = string
}

variable "name_prefix" {
  description = "Prefix for tagging resources"
  type        = string
  default     = "cloudinfra-static-site"
}
