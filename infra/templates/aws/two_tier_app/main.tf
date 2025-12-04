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

# Use default VPC + a subnet for simplicity
data "aws_vpc" "default" {
  default = true
}

data "aws_subnet_ids" "default_subnets" {
  vpc_id = data.aws_vpc.default.id
}

# Security group for web EC2
resource "aws_security_group" "web_sg" {
  name        = "two-tier-web-sg"
  description = "Allow HTTP and SSH"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "two-tier-web-sg"
  }
}

# Security group for RDS – allow MySQL from web SG only
resource "aws_security_group" "db_sg" {
  name        = "two-tier-db-sg"
  description = "Allow MySQL from web security group"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "MySQL from web SG"
    from_port   = 3306
    to_port     = 3306
    protocol    = "tcp"
    security_groups = [
      aws_security_group.web_sg.id
    ]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "two-tier-db-sg"
  }
}

# Subnet group for RDS
resource "aws_db_subnet_group" "db_subnets" {
  name       = "two-tier-db-subnet-group"
  subnet_ids = data.aws_subnet_ids.default_subnets.ids

  tags = {
    Name = "two-tier-db-subnet-group"
  }
}

# RDS MySQL instance (publicly accessible for learning/demo)
resource "aws_db_instance" "db" {
  allocated_storage    = var.db_allocated_storage
  engine               = "mysql"
  engine_version       = "8.0"
  instance_class       = var.db_instance_class
  identifier           = "two-tier-db"
  username             = var.db_username
  password             = var.db_password
  db_name              = var.db_name
  skip_final_snapshot  = true
  publicly_accessible  = true

  vpc_security_group_ids = [aws_security_group.db_sg.id]
  db_subnet_group_name   = aws_db_subnet_group.db_subnets.name

  tags = {
    Name = "two-tier-db"
  }
}

# AMI for Amazon Linux 2023
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

# Web EC2 instance
resource "aws_instance" "web" {
  ami           = data.aws_ami.amazon_linux.id
  instance_type = "t2.micro"
  key_name      = var.key_pair_name

  subnet_id              = data.aws_subnet_ids.default_subnets.ids[0]
  vpc_security_group_ids = [aws_security_group.web_sg.id]
  associate_public_ip_address = true

  tags = {
    Name = var.instance_name
    Tier = "web"
  }

  user_data = <<-EOF
              #!/bin/bash
              yum update -y
              yum install -y httpd mysql

              systemctl enable httpd
              systemctl start httpd

              echo "<h1>CloudInfra Two-Tier App</h1>" > /var/www/html/index.html
              echo "<p>Web server: ${var.instance_name}</p>" >> /var/www/html/index.html
              echo "<p>DB endpoint: ${aws_db_instance.db.address}</p>" >> /var/www/html/index.html
              echo "<p>DB name: ${var.db_name}</p>" >> /var/www/html/index.html
              EOF
}

