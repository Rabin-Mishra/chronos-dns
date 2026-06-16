variable "aws_region" {
  type        = string
  description = "The AWS region to deploy resources in"
  default     = "ap-south-1"
}

variable "project_name" {
  type        = string
  description = "Project name tag value used to label resources"
  default     = "chronos-dns"
}

variable "environment" {
  type        = string
  description = "Deployment environment name"
  default     = "dev"
}

variable "instance_type" {
  type        = string
  description = "EC2 instance size for the measurement probe"
  default     = "t2.micro"
}

variable "ami_id" {
  type        = string
  description = "AMI ID override. Leave empty to auto-fetch latest Ubuntu 22.04 LTS in the target region."
  default     = ""
}

variable "ssh_public_key_path" {
  type        = string
  description = "Local path to the SSH public key for EC2 access"
  default     = "~/.ssh/id_rsa.pub"
}

variable "cloudflare_tunnel_token" {
  type        = string
  description = "The Cloudflare Tunnel token for zero inbound port connectivity"
  sensitive   = true
  default     = ""
}

variable "my_ip_cidr" {
  type        = string
  description = "Your local machine IP in CIDR notation for SSH access restriction (e.g. 203.0.113.5/32)"
  default     = ""
}

variable "key_pair_name" {
  type        = string
  description = "Name of the AWS EC2 key pair to use for SSH access"
  default     = "chronos-dns-key"
}
