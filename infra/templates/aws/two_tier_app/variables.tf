variable "aws_region" {
  description = "AWS region to deploy the app"
  type        = string
}

variable "instance_name" {
  description = "Name for the web EC2 instance"
  type        = string
}

variable "key_pair_name" {
  description = "Existing AWS key pair name for SSH"
  type        = string
}

variable "db_name" {
  description = "Database name for RDS"
  type        = string
}

variable "db_username" {
  description = "Master username for RDS"
  type        = string
}

variable "db_password" {
  description = "Master password for RDS"
  type        = string
  sensitive   = true
}

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.micro"
}

variable "db_allocated_storage" {
  description = "Storage in GB for RDS"
  type        = number
  default     = 20
}
