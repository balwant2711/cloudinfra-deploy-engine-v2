variable "aws_region" {
  description = "AWS region to deploy the ALB + ASG app"
  type        = string
}

variable "instance_name" {
  description = "Name prefix for the web instances"
  type        = string
}

variable "key_pair_name" {
  description = "Existing AWS key pair name for SSH"
  type        = string
}

variable "asg_instance_type" {
  description = "Instance type for Auto Scaling Group"
  type        = string
  default     = "t2.micro"
}

variable "asg_desired_capacity" {
  description = "Desired number of EC2 instances"
  type        = number
  default     = 2
}

variable "asg_min_size" {
  description = "Minimum number of EC2 instances"
  type        = number
  default     = 1
}

variable "asg_max_size" {
  description = "Maximum number of EC2 instances"
  type        = number
  default     = 3
}
