# AGENTS.md — Chronos-DNS

## Project overview
Cloud-native distributed measurement fabric tracking DNS-over-HTTPS (DoH)
and DNS-over-TLS (DoT) latency and deployment anomalies globally.
Research proof-of-concept for MEXT Scholarship (WIDE Project alignment).
Builder: Rabin Mishra — ASUS TUF A15, Ubuntu 24.04, AMD Ryzen 7 6800H.

## Stack
- Infrastructure: Terraform 1.15.6 (AWS EC2, VPC, S3 state, DynamoDB lock)
- Config management: Ansible core 2.21.0 (Ubuntu hardening, Docker, Nginx)
- Probe: Python 3.12, dnspython, httpx, Pandas, FastAPI
- Containers: Docker 29.5.3, Docker Compose v5.1.4
- Networking: Cloudflare Tunnels (zero open inbound ports)
- CI/CD: GitHub Actions (multi-stage Docker build, push to GHCR, deploy EC2)
- Observability: Prometheus, Grafana, PostgreSQL (Neon)
- AWS region: ap-south-1 (Mumbai)

## Directory layout
chronos-dns/
├── infra/
│   ├── terraform/
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   ├── outputs.tf
│   │   ├── backend.tf
│   │   └── modules/
│   └── ansible/
│       ├── playbook.yml
│       └── roles/
├── probe/
│   ├── probe.py
│   ├── models.py
│   ├── targets.json
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── tests/
│       └── test_probe.py
├── observe/
│   ├── prometheus.yml
│   ├── docker-compose.yml
│   └── grafana/
│       └── provisioning/
├── .github/
│   └── workflows/
│       └── ci.yml
├── .env.example
├── .gitignore
├── AGENTS.md
└── README.md

## Hard rules for all agents
- All secrets via environment variables only — never hardcoded
- Python: type hints and docstrings on every function
- Terraform: tag every resource with Project=chronos-dns, Environment=dev
- AWS region is always ap-south-1
- Never run terraform destroy without asking me first
- Never commit .env files — only .env.example with empty values
