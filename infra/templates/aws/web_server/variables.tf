variable "instance_name" {
  description = "Name tag for the EC2 instance"
  type        = string
}

variable "key_pair_name" {
  description = "Existing AWS key pair name to associate with the instance"
  type        = string
}

variable "aws_region" {
  description = "AWS Region in which to deploy the instance"
  type        = string
}
