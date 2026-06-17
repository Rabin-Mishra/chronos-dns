# Chronos-DNS System Architecture 🌐

This document details the technical architecture, data flows, network topology, and CI/CD operations of the Chronos-DNS distributed measurement fabric.

---

## 1. Core Measurement Cycle

The `chronos-dns-probe` engine is designed as an asynchronous, non-blocking telemetry collector built on Python 3.12 and FastAPI. It runs on a continuous 30-second loop to measure latency and verify certificate chains across standard and encrypted DNS protocols.

```mermaid
sequenceDiagram
    participant Loop as Measurement Loop
    participant JSON as targets.json
    participant Engine as Async Measurement Engine
    participant Resolvers as Target Resolvers (DNS/DoH/DoT)
    participant Prom as Prometheus Metrics Registry
    participant DB as PostgreSQL (Neon)

    Loop->>JSON: load_targets()
    JSON-->>Loop: Target Configurations (IPs, Endpoints, Hosts)
    Loop->>Engine: Group by Resolver & Protocol (asyncio.gather)
    par plain DNS
        Engine->>Resolvers: UDP Query (Port 53)
        Resolvers-->>Engine: RTT & Status
    and DoH
        Engine->>Resolvers: HTTPS POST Query (Port 443)
        Resolvers-->>Engine: RTT, TLS Handshake, HTTPS Status
    and DoT
        Engine->>Resolvers: SSL wrapped Socket TCP (Port 853)
        Resolvers-->>Engine: RTT, TLS Handshake, Cert Details
    end
    Engine->>Prom: Expose Metrics via /metrics
    Engine->>DB: Ingest Telemetry Records (SQLAlchemy commit)
```

### Flow Breakdown:
1. **Target Loading**: The probe loads targets dynamically from [targets.json](file:///home/rabin/Documents/MEXT_WIDE/chronos-dns/probe/targets.json).
2. **Concurrent Inquiries**: Using `asyncio.gather`, the engine runs parallel measurement tasks to prevent slower endpoints from blocking faster ones:
    - **Standard DNS**: Uses `dnspython` udp query wrapper to measure standard unencrypted latency on UDP port 53.
    - **DNS-over-HTTPS (DoH)**: Utilizes `httpx` async client to send DNS wireformat payloads over HTTP POST requests on port 443, capturing server response times, HTTP statuses, and calculating network-to-TLS latency delta.
    - **DNS-over-TLS (DoT)**: Directly opens standard socket connections, wraps them with standard SSL contexts to verify X.509 certificates, extracts validity timestamps (`notAfter`), and measures TCP connection and TLS handshake times on TCP port 853.
3. **Metrics Exposition**: Prometheus-compatible counters and gauges are updated on the fly. The FastAPI instance serves this data at `/metrics`.
4. **Relational Storage**: The engine commits detailed telemetry packets to the remote serverless PostgreSQL instance (Neon) using the SQLAlchemy ORM for long-term historical analysis.

---

## 2. Network Topology

To maintain a secure infrastructure footprint, the probe node runs with **zero open inbound firewall ports**. Traffic flows securely using Cloudflare Tunnels.

```
+-----------------------------------------------------------------------------------+
|                              AWS EC2 (ap-south-1)                                 |
|                                                                                   |
|   +------------------------------------+                                          |
|   |         Docker Containers          |                                          |
|   |                                    |                                          |
|   |  +------------------------------+  |  Scrape (10s)                            |
|   |  |   chronos-dns-probe:8000     |<-----------------------+                    |
|   |  +------------------------------+  |                         |                |
|   |                                    |                         |                |
|   |  +------------------------------+  |                         |                |
|   |  |   chronos-prometheus:9090    |------------------------+                    |
|   |  +------------------------------+  |  Write                                   |
|   |                                    |                                          |
|   |  +------------------------------+  |                                          |
|   |  |    chronos-grafana:3000      |  |                                          |
|   |  +------------------------------+  |                                          |
|   +-------------------|----------------+                                          |
|                       |                                                           |
|                       | Internal reverse proxy via Docker Network                 |
|                       v                                                           |
|               +---------------+                                                   |
|               |  cloudflared  | (Cloudflare Tunnel Client Daemon)                 |
|               +-------|-------+                                                   |
+-----------------------|-----------------------------------------------------------+
                        |
                        | Secure Outbound Tunnel over HTTPS (TCP 443)
                        v
             +--------------------+
             | Cloudflare Edge    |
             +---------|----------+
                       |
                       | Web Browser (Dashboard View)
                       v
             +--------------------+
             |   End User         | (Accessing dashboard on port 3000)
             +--------------------+
```

### Components & Security Boundaries:
- **Zero Inbound Architecture**: AWS Security Groups only allow outbound connections. The `cloudflared` daemon creates multiple secure TCP pools to the closest Cloudflare edge nodes, routing Grafana web access securely without opening port 3000 or 80 to the public internet.
- **Docker Isolation**: All telemetry probe operations, Prometheus metrics databases, Grafana dashboards, and OS resource exporters (`node-exporter`) reside in decoupled Docker bridged networks.

---

## 3. CI/CD Pipeline Flow

GitHub Actions handles automated validation and continuous deployment to ensure code safety before it runs in production.

```
[ Git Push to main ]
         │
         ▼
 ┌───────────────┐
 │   Lint Job    │  (Checks styling consistency using ruff check)
 └───────┬───────┘
         │ (Success)
         ▼
 ┌───────────────┐
 │   Test Job    │  (Executes pytest, mocks network requests, validates SQLite)
 └───────┬───────┘
         │ (Success)
         ▼
 ┌───────────────┐
 │   Build Job   │  (Runs Docker multi-stage build, labels, pushes image to GHCR)
 └───────┬───────┘
         │ (Success)
         ▼
 ┌───────────────┐
 │  Deploy Job   │  (SSH via Actions EC2, pulls latest GHCR image, recreates container)
 └───────────────┘
```

### Pipeline Integrity:
- **Multi-Stage Dockerfile**: Builds are isolated, utilizing caching layers for Python packages. The final image size is reduced (<150MB) and runs with a non-root system user (`chronos`) for enhanced container safety.
- **Automatic Deployment Rollbacks**: If any test fails during the `Test` stage, the pipeline halts immediately, keeping the previous stable image running on EC2.

---

## 4. Alignment with WIDE Project Research

The **WIDE Project** (Widely Integrated Distributed Environment) runs foundational research for the global Internet, operating the **M Root DNS Server** and maintaining the **MAWI** network traffic archives. 

Chronos-DNS aligns directly with WIDE's core objectives by demonstrating:
1. **Adoption Profiling**: Measuring what portion of DNS clients successfully transition to modern encrypted protocols (DoH and DoT).
2. **Performance Characterization**: Empirically measuring TLS handshake latencies to determine if cryptographic negotiations introduce unacceptable latency overheads in various geographical cloud regions.
3. **Security Auditing**: Actively tracking certificate renewal velocities and remaining certificate lifespans to detect configuration errors before they cause resolver outages.
4. **Resiliency Mapping**: Isolating protocol-level failure modes (timeouts, refused connections, fallback to plaintext) to evaluate the robustness of encrypted DNS infrastructure.
