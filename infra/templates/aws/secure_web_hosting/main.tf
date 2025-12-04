terraform {
  required_version = ">= 1.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# Default VPC + subnets
data "aws_vpc" "default" {
  default = true
}

data "aws_subnet_ids" "default_subnets" {
  vpc_id = data.aws_vpc.default.id
}

# Latest Amazon Linux
data "aws_ami" "amazon_linux" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}

# Security group for secure web server
resource "aws_security_group" "secure_web_sg" {
  name        = "${var.instance_name}-secure-web-sg"
  description = "Secure web hosting security group"
  vpc_id      = data.aws_vpc.default.id

  # HTTP from anywhere
  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # HTTPS from anywhere (for future TLS)
  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # SSH only from allowed CIDR
  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ssh_cidr]
  }

  # Outbound
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.instance_name}-secure-web-sg"
  }
}

# EC2 instance
resource "aws_instance" "secure_web" {
  ami                    = data.aws_ami.amazon_linux.id
  instance_type          = var.instance_type
  key_name               = var.key_pair_name
  subnet_id              = data.aws_subnet_ids.default_subnets.ids[0]
  vpc_security_group_ids = [aws_security_group.secure_web_sg.id]
  associate_public_ip_address = true

  tags = {
    Name = var.instance_name
    Role = "secure-web-server"
  }

  user_data = <<-EOF
              #!/bin/bash
              set -e

              # Update system
              yum update -y

              # Install nginx + git
              yum install -y nginx git

              # Enable + start nginx
              systemctl enable nginx
              systemctl start nginx

              # Harden SSH: disable password auth (key-based only)
              sed -i 's/^#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
              sed -i 's/^PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
              systemctl restart sshd

              # Clone GitHub repo
              mkdir -p /var/www/app
              cd /var/www/app
              git clone -b ${var.github_branch} ${var.github_repo_url} repo || {
                echo "Git clone failed" > /var/www/html/error.html
              }

              APP_ROOT="/var/www/app/repo"
              # Optional subdir inside repo (e.g. dist, build)
              if [ "${var.app_root_subdir}" != "" ]; then
                APP_ROOT="${APP_ROOT}/${var.app_root_subdir}"
              fi

              # If build step is needed (simple example: npm run build), that can be added here
              # For now we assume static files already present in repo root or subdir.

              # Configure nginx to serve from APP_ROOT
              cat > /etc/nginx/conf.d/secure_site.conf <<NGINXCONF
              server {
                  listen       80;
                  server_name  ${var.domain_name};

                  root   ${APP_ROOT};
                  index  index.html index.htm;
