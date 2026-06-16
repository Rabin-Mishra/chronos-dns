output "instance_id" {
  description = "The EC2 Instance ID of the measurement probe"
  value       = aws_instance.probe.id
}

output "probe_public_ip" {
  description = "The public IP address of the measurement probe"
  value       = aws_instance.probe.public_ip
}

output "probe_public_dns" {
  description = "The public DNS name of the measurement probe"
  value       = aws_instance.probe.public_dns
}

output "vpc_id" {
  description = "The VPC ID created for Chronos-DNS"
  value       = aws_vpc.main.id
}
