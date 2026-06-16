terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    http = {
      source  = "hashicorp/http"
      version = "~> 3.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# Fetch the latest Ubuntu 22.04 LTS AMI if not overridden
data "aws_ami" "ubuntu" {
  count       = var.ami_id == "" ? 1 : 0
  most_recent = true

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  owners = ["099720109477"] # Canonical
}

# Automatically fetch local public IP
data "http" "my_ip" {
  url = "https://checkip.amazonaws.com"
}

locals {
  ami_id     = var.ami_id != "" ? var.ami_id : data.aws_ami.ubuntu[0].id
  my_ip_cidr = "${chomp(data.http.my_ip.response_body)}/32"
  common_tags = {
    Project     = "chronos-dns"
    Environment = "dev"
  }
}

# Key Pair for SSH Access
resource "aws_key_pair" "probe_key" {
  key_name   = var.key_pair_name
  public_key = file(var.ssh_public_key_path)
  tags       = local.common_tags
}

# VPC Configuration
resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = merge(
    local.common_tags,
    {
      Name = "${var.project_name}-vpc"
    }
  )
}

# Internet Gateway
resource "aws_internet_gateway" "gw" {
  vpc_id = aws_vpc.main.id

  tags = merge(
    local.common_tags,
    {
      Name = "${var.project_name}-igw"
    }
  )
}

# Public Subnet
resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.1.0/24"
  availability_zone       = "${var.aws_region}a"
  map_public_ip_on_launch = true

  tags = merge(
    local.common_tags,
    {
      Name = "${var.project_name}-public-subnet"
    }
  )
}

# Route Table
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.gw.id
  }

  tags = merge(
    local.common_tags,
    {
      Name = "${var.project_name}-public-rt"
    }
  )
}

# Route Table Association
resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# Security Group
resource "aws_security_group" "probe_sg" {
  name        = "${var.project_name}-probe-sg"
  description = "Security group for Chronos-DNS probe EC2 instance"
  vpc_id      = aws_vpc.main.id

  # Inbound SSH restricted to user's IP
  ingress {
    description = "Restricted SSH access"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [local.my_ip_cidr]
  }

  # Outbound rules - Allow all egress to perform measurements and connect to Cloudflare
  egress {
    description = "Allow all outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(
    local.common_tags,
    {
      Name = "${var.project_name}-sg"
    }
  )
}

# EC2 Instance for Probe Node
resource "aws_instance" "probe" {
  ami                    = local.ami_id
  instance_type          = var.instance_type
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.probe_sg.id]
  key_name               = aws_key_pair.probe_key.key_name

  # Enable resource termination protection for research stability
  disable_api_termination = true

  # User data placeholder to install docker, ansible prerequisites, etc.
  user_data = <<-EOF
              #!/bin/bash
              # TODO: Add initialization shell script actions or leave to Ansible
              EOF

  tags = merge(
    local.common_tags,
    {
      Name = "${var.project_name}-probe-instance"
    }
  )
}
