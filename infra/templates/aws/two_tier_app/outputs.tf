output "web_public_ip" {
  description = "Public IP of the web instance"
  value       = aws_instance.web.public_ip
}

output "web_public_dns" {
  description = "Public DNS of the web instance"
  value       = aws_instance.web.public_dns
}

output "db_endpoint" {
  description = "RDS DB endpoint"
  value       = aws_db_instance.db.address
}
