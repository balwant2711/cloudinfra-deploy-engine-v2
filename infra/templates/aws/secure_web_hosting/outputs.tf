output "instance_public_ip" {
  description = "Public IP of the secure web server"
  value       = aws_instance.secure_web.public_ip
}

output "instance_public_dns" {
  description = "Public DNS of the secure web server"
  value       = aws_instance.secure_web.public_dns
}

output "security_group_id" {
  description = "Security group ID used for the server"
  value       = aws_security_group.secure_web_sg.id
}
