variable "aws_region" {
  description = "AWS region to deploy the secure web server"
  type        = string
}

variable "instance_name" {
  description = "Name for the secure web EC2 instance"
  type        = string
}

variable "key_pair_name" {
  description = "Existing AWS key pair name for SSH"
  type        = string
}

variable "allowed_ssh_cidr" {
  description = "CIDR allowed to SSH into the server (e.g. your IP /32)"
  type        = string
  default     = "0.0.0.0/0"
}

variable "instance_type" {
  description = "Instance type for the web server"
  type        = string
  default     = "t3.micro"
}

variable "github_repo_url" {
  description = "Public GitHub repository URL for the website/app code"
  type        = string
}

variable "github_branch" {
  description = "Git branch to deploy"
  type        = string
  default     = "main"
}

variable "app_root_subdir" {
  description = "Optional subdirectory inside the repo to use as web root (e.g. 'dist' or 'build'). Leave empty for repo root."
  type        = string
  default     = ""
}

variable "domain_name" {
  description = "Domain name (for documentation / nginx config) e.g. example.com"
  type        = string
}
