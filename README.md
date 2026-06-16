# Chronos-DNS 🌐

> An automated, cloud-native distributed measurement fabric for empirical
> analysis of DNS-over-HTTPS (DoH) and DNS-over-TLS (DoT) deployment,
> latency, and cryptographic compliance across global internet environments.

---

## Research Context

This project is the practical proof-of-concept for my **MEXT Scholarship**
research proposal submitted to the Embassy of Japan in Nepal
(Registration No. 41):

**"Empirical Measurement of DNS Security Protocol Deployment and Its
Relationship to Cloud Infrastructure Reliability in Real-World Internet
Environments"**

### Target Institution
This project is designed to demonstrate research readiness for the
**WIDE Project** (Widely Integrated Distributed Environment) — the
legendary Japanese research consortium that operates the **M Root DNS
Server** and runs the **MAWI Working Group** for internet traffic
measurement and analysis. Affiliated universities include Keio University,
the University of Tokyo, and Tokyo Institute of Technology.

### Research Problem
The global internet is undergoing a critical security transition. Legacy
plaintext DNS (UDP port 53) exposes user queries to surveillance and
manipulation. DNS-over-HTTPS (DoH) and DNS-over-TLS (DoT) encrypt this
traffic — but real-world adoption is uneven, and the performance and
reliability implications of this transition are not well-understood at
scale. Chronos-DNS builds the measurement infrastructure to study this
empirically.

---

## What Chronos-DNS Does

Chronos-DNS deploys lightweight measurement probe nodes across multiple
cloud regions. Each probe periodically fires DNS, DoH, and DoT queries
to a curated list of public resolvers (Cloudflare, Google, Quad9, Mullvad,
and others), capturing:

- Round-trip time (RTT) in milliseconds per protocol
- TLS handshake duration for encrypted resolvers
- Certificate validity and expiry dates
- Query success/failure rates and failure reasons
- Protocol-level anomalies (fallback behaviour, timeout patterns)

All telemetry is ingested into a central PostgreSQL database, visualised
in real-time Grafana dashboards, and stored for longitudinal analysis
using Pandas and NumPy.

---

## Architecture
┌─────────────────────────────────────────────────────────────────┐

│                        EDGE LAYER                               │

│                                                                 │

│   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐         │

│   │  Probe Node │   │  Probe Node │   │  Probe Node │         │

│   │  EC2 t2.micro│  │  EC2 t2.micro│  │  EC2 t2.micro│        │

│   │  ap-south-1 │   │  (future)   │   │  (future)   │         │

│   └──────┬──────┘   └─────────────┘   └─────────────┘         │

│          │  Python probe.py                                     │

│          │  DNS / DoH / DoT queries → targets.json             │

└──────────┼──────────────────────────────────────────────────────┘

│

│  Cloudflare Tunnel (zero open inbound ports)

│

┌──────────▼──────────────────────────────────────────────────────┐

│                      INGESTION LAYER                            │

│                                                                 │

│   FastAPI /ingest endpoint  ←  probe telemetry (JSON)          │

│   SQLAlchemy ORM                                                │

│   PostgreSQL on Neon (managed, serverless)                      │

│                                                                 │

└──────────┬──────────────────────────────────────────────────────┘

│

┌──────────▼──────────────────────────────────────────────────────┐

│                    OBSERVABILITY LAYER                          │

│                                                                 │

│   Prometheus  →  scrapes /metrics from FastAPI                 │

│   Grafana     →  dashboards (RTT heatmap, success rate,        │

│                  TLS latency P50/P95, cert expiry table)       │

│   Alerting    →  fires if success_rate < 90% for 5 minutes     │

│                                                                 │

└──────────┬──────────────────────────────────────────────────────┘

│

┌──────────▼──────────────────────────────────────────────────────┐

│                      ANALYSIS LAYER                             │

│                                                                 │

│   Pandas + NumPy  →  batch analysis of collected datasets      │

│   Correlation:  DNSSEC presence vs packet loss                 │

│   Correlation:  cipher suite strength vs latency               │

│   Output:  research-grade CSV + visualisation exports          │

│                                                                 │

└─────────────────────────────────────────────────────────────────┘


---

## Technical Stack

| Layer | Technology | Version | Purpose |
|---|---|---|---|
| Infrastructure as Code | Terraform | 1.15.6 | Provision AWS EC2, VPC, S3, DynamoDB |
| Configuration management | Ansible | core 2.21.0 | Server hardening, Docker install, Cloudflare tunnel setup |
| Measurement probe | Python | 3.12 | DNS/DoH/DoT query engine |
| DNS library | dnspython | latest | Standard DNS query handling |
| HTTP client | httpx | latest | DoH queries over HTTPS with TLS metrics |
| Data processing | Pandas + NumPy | latest | Telemetry structuring and analysis |
| API framework | FastAPI | latest | Ingest endpoint + /metrics exposure |
| Containerisation | Docker | 29.5.3 | Probe packaging and deployment |
| Container orchestration | Docker Compose | v5.1.4 | Multi-service local and remote deployment |
| Secure networking | Cloudflare Tunnels | 2026.5.2 | Zero open inbound ports on probe nodes |
| CI/CD | GitHub Actions | — | Lint, test, build, push, deploy pipeline |
| Metrics collection | Prometheus | latest | Scrape probe /metrics endpoint |
| Visualisation | Grafana | latest | Real-time dashboards and alerting |
| Database | PostgreSQL on Neon | 15 | Telemetry storage, serverless managed |
| Cloud provider | AWS | — | EC2 compute, ap-south-1 region (Mumbai) |
| State backend | AWS S3 + DynamoDB | — | Terraform remote state with locking |

---

## Repository Structure
chronos-dns/

│

├── infra/                          # Infrastructure as Code

│   ├── terraform/

│   │   ├── main.tf                 # VPC, EC2, Security Groups

│   │   ├── variables.tf            # Input variables

│   │   ├── outputs.tf              # EC2 IP, instance ID

│   │   ├── backend.tf              # S3 remote state config

│   │   └── modules/

│   │       └── state/              # S3 + DynamoDB state module

│   └── ansible/

│       ├── playbook.yml            # Master playbook

│       └── roles/

│           ├── harden/             # UFW, fail2ban, SSH hardening

│           ├── docker/             # Docker Engine install

│           └── cloudflared/        # Cloudflare Tunnel setup

│

├── probe/                          # Measurement probe

│   ├── probe.py                    # Core query engine (DNS/DoH/DoT)

│   ├── models.py                   # SQLAlchemy database models

│   ├── targets.json                # List of resolvers to measure

│   ├── Dockerfile                  # Multi-stage, non-root, <150MB

│   ├── docker-compose.yml          # Probe + local postgres for dev

│   └── tests/

│       └── test_probe.py           # pytest test suite

│

├── observe/                        # Observability stack

│   ├── prometheus.yml              # Scrape config + alert rules

│   ├── docker-compose.yml          # Prometheus + Grafana + node-exporter

│   └── grafana/

│       └── provisioning/

│           ├── datasources/        # Auto-provision Prometheus source

│           └── dashboards/         # Chronos-DNS dashboard JSON

│

├── .github/

│   └── workflows/

│       └── ci.yml                  # Lint → test → build → deploy

│

├── .env.example                    # Variable names, no real secrets

├── .gitignore                      # Python, Terraform, env, OS files

├── AGENTS.md                       # AI agent context and rules

└── README.md                       # This file

---

## DNS Resolvers Under Measurement

| Resolver | Operator | DoH Endpoint | DoT Host |
|---|---|---|---|
| 1.1.1.1 | Cloudflare | `https://cloudflare-dns.com/dns-query` | `one.one.one.one:853` |
| 8.8.8.8 | Google | `https://dns.google/dns-query` | `dns.google:853` |
| 9.9.9.9 | Quad9 | `https://dns.quad9.net/dns-query` | `dns.quad9.net:853` |
| 94.140.14.14 | AdGuard | `https://dns.adguard.com/dns-query` | `dns.adguard.com:853` |
| 194.242.2.2 | Mullvad | `https://doh.mullvad.net/dns-query` | `doh.mullvad.net:853` |
| 185.228.168.9 | CleanBrowsing | `https://doh.cleanbrowsing.org/doh/family-filter` | `family-filter-dns.cleanbrowsing.org:853` |

---

## Metrics Captured Per Query

| Metric | Type | Labels | Description |
|---|---|---|---|
| `probe_rtt_seconds` | Histogram | resolver, protocol | End-to-end query round-trip time |
| `probe_tls_handshake_seconds` | Histogram | resolver | TLS handshake duration (DoH/DoT only) |
| `probe_success_total` | Counter | resolver, protocol | Successful query count |
| `probe_failures_total` | Counter | resolver, protocol, reason | Failed query count with reason |
| `probe_cert_expiry_days` | Gauge | resolver | Days until TLS certificate expires |

---

## CI/CD Pipeline
Push to main

│

▼

┌─────────┐    ┌──────────┐    ┌───────────────┐    ┌────────────┐

│  Lint   │ →  │  Test    │ →  │  Docker Build │ →  │  Deploy    │

│  ruff   │    │  pytest  │    │  push to GHCR │    │  SSH → EC2 │

│  check  │    │  coverage│    │  multi-stage  │    │  compose up│

└─────────┘    └──────────┘    └───────────────┘    └────────────┘

Every push triggers the full pipeline. A failed test blocks deployment.
Build status and coverage reports appear in the GitHub Actions summary.

---

## Getting Started (Development)

```bash
# Clone
git clone https://github.com/Rabin-Mishra/chronos-dns.git
cd chronos-dns

# Copy and fill environment variables
cp .env.example .env
nano .env

# Install Python dependencies
pip3 install dnspython httpx pandas numpy fastapi uvicorn \
  pytest pytest-asyncio python-dotenv prometheus-client \
  psycopg2-binary sqlalchemy --break-system-packages

# Run the probe locally
cd probe && python3 probe.py

# Run tests
pytest tests/ -v --tb=short

# Start full local stack
docker compose up -d
```

---

## Infrastructure Setup

```bash
# Provision AWS infrastructure
cd infra/terraform
terraform init
terraform plan
terraform apply

# Configure and harden the EC2 node
cd ../ansible
ansible-playbook playbook.yml -i inventory.ini
```

---

## Research Alignment with WIDE Project

The WIDE Project has operated the M Root DNS Server since 1997 and
produces the MAWI dataset — one of the world's longest-running internet
traffic archives. Chronos-DNS is designed as a miniature version of the
kind of measurement infrastructure WIDE operates at scale.

When scaled using WIDE's infrastructure and the MAWI datasets,
Chronos-DNS's methodology can answer:

- What percentage of global DNS traffic is now encrypted?
- Which cloud regions show the highest DoT/DoH adoption?
- Do DNSSEC-signed zones correlate with lower packet loss?
- How does resolver geography affect TLS handshake latency?

---

## Author

**Rabin Mishra**
MEXT Scholarship Applicant — Embassy of Japan in Nepal (No. 41)
Target: WIDE Project, Japan
GitHub: [github.com/Rabin-Mishra](https://github.com/Rabin-Mishra)

---

## Status

| Component | Status |
|---|---|
| Repository scaffold | ✅ Complete |
| Terraform infrastructure | 🔨 In progress |
| Python probe engine | 🔨 In progress |
| Docker + CI/CD pipeline | 🔨 In progress |
| Observability stack | 🔨 In progress |
| Ansible hardening | 🔨 In progress |
| Grafana dashboards | ⏳ Planned |
| Multi-region deployment | ⏳ Planned |
| Research analysis notebooks | ⏳ Planned |

---

*Built as a research proof-of-concept. Not intended for production use
without further security review.*