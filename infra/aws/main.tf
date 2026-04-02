# ══════════════════════════════════════════════════════════
# OpenMTSN — AWS Free Tier Deployment
# ══════════════════════════════════════════════════════════
# Provisions: EC2 t2.micro + Security Groups + Docker runtime
# Cost: $0 (within AWS Free Tier limits)
# ══════════════════════════════════════════════════════════

terraform {
  required_version = ">= 1.5"
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

# ── Variables ─────────────────────────────────────────────

variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "us-east-1"
}

variable "key_pair_name" {
  description = "EC2 key pair for SSH access"
  type        = string
  default     = "openmtsn-key"
}

variable "ghcr_token" {
  description = "GitHub Container Registry PAT for pulling images"
  type        = string
  sensitive   = true
  default     = ""
}

# ── Data Sources ──────────────────────────────────────────

data "aws_ami" "amazon_linux" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# ── Security Group ────────────────────────────────────────

resource "aws_security_group" "mtsn" {
  name        = "openmtsn-sg"
  description = "OpenMTSN - Allow HTTP, HTTPS, MQTT, SSH"

  # SSH
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "SSH access"
  }

  # HTTP (Dashboard)
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Dashboard HTTP"
  }

  # HTTPS
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Dashboard HTTPS"
  }

  # FastAPI
  ingress {
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "API endpoint"
  }

  # MQTT
  ingress {
    from_port   = 1883
    to_port     = 1883
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "MQTT broker"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "All outbound"
  }

  tags = {
    Name    = "openmtsn-security-group"
    Project = "OpenMTSN"
  }
}

# ── EC2 Instance (Free Tier: t2.micro) ───────────────────

resource "aws_instance" "mtsn_server" {
  ami                    = data.aws_ami.amazon_linux.id
  instance_type          = "t2.micro"
  key_name               = var.key_pair_name
  vpc_security_group_ids = [aws_security_group.mtsn.id]

  root_block_device {
    volume_size = 20   # GB (free tier allows up to 30 GB EBS)
    volume_type = "gp3"
    encrypted   = true
  }

  user_data = <<-USERDATA
    #!/bin/bash
    set -e

    # Install Docker
    yum update -y
    yum install -y docker git
    systemctl start docker
    systemctl enable docker
    usermod -aG docker ec2-user

    # Install Docker Compose
    COMPOSE_VERSION="v2.27.1"
    curl -SL "https://github.com/docker/compose/releases/download/$${COMPOSE_VERSION}/docker-compose-linux-x86_64" \
      -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
    ln -sf /usr/local/bin/docker-compose /usr/bin/docker-compose

    # Clone and deploy
    mkdir -p /opt/openmtsn
    cd /opt/openmtsn

    # Pull images from GHCR (if token provided)
    if [ -n "${var.ghcr_token}" ]; then
      echo "${var.ghcr_token}" | docker login ghcr.io -u openmtsn --password-stdin
    fi

    # Create docker-compose for production
    cat > docker-compose.yml << 'COMPOSE'
    services:
      mqtt-broker:
        image: eclipse-mosquitto:2
        restart: always
        ports: ["1883:1883"]

      redis:
        image: redis:7-alpine
        restart: always

      api:
        image: ghcr.io/openmtsn/openmtsn/api:latest
        restart: always
        ports: ["8000:8000"]
        environment:
          MTSN_REDIS_URL: "redis://redis:6379/0"
        depends_on: [redis]

      dashboard:
        image: ghcr.io/openmtsn/openmtsn/dashboard:latest
        restart: always
        ports: ["80:80"]
        depends_on: [api]
    COMPOSE

    docker-compose up -d
  USERDATA

  tags = {
    Name    = "openmtsn-server"
    Project = "OpenMTSN"
  }
}

# ── Outputs ──────────────────────────────────────────────

output "public_ip" {
  description = "Public IP of the OpenMTSN server"
  value       = aws_instance.mtsn_server.public_ip
}

output "dashboard_url" {
  description = "URL for the Command Center dashboard"
  value       = "http://${aws_instance.mtsn_server.public_ip}"
}

output "api_url" {
  description = "URL for the API documentation"
  value       = "http://${aws_instance.mtsn_server.public_ip}:8000/docs"
}

output "ssh_command" {
  description = "SSH command to connect to the server"
  value       = "ssh -i ${var.key_pair_name}.pem ec2-user@${aws_instance.mtsn_server.public_ip}"
}
