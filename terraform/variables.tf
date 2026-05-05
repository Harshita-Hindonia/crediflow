variable "aws_region"   { default = "us-east-1" }
variable "project_name" { default = "creditflow" }
variable "environment"  { default = "dev" }

variable "backend_cpu"          { default = 256 }
variable "backend_memory"       { default = 512 }
variable "backend_image_tag"    { default = "latest" }
variable "alert_email"          { default = "harshitahindonia@gmail.com" }

locals {
  prefix = "${var.project_name}-${var.environment}"
}
