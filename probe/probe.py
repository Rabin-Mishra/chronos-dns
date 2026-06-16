"""
Chronos-DNS Probe Engine.
Performs periodic DNS, DoH, and DoT latency/anomaly measurements,
publishes Prometheus metrics, and ingests telemetry data into PostgreSQL.
"""

import asyncio
import os
import time
import json
import socket
import ssl
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, AsyncGenerator, Optional
from urllib.parse import urlparse

import httpx
import dns.message
import dns.query
import dns.rdatatype
from fastapi import FastAPI, BackgroundTasks, Depends, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from sqlalchemy.orm import Session

from models import DNSMeasurement, get_db, init_db, SessionLocal

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Lifespan context manager for initialising the database.
    """
    init_db()
    task = asyncio.create_task(measurement_loop())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

# Initialize FastAPI application with lifespan
app = FastAPI(title="Chronos-DNS Probe API", version="1.0.0", lifespan=lifespan)

# Prometheus Metrics definition
PROBE_RTT = Histogram(
    "probe_rtt_seconds",
    "End-to-end query round-trip time",
    ["resolver", "protocol"]
)
PROBE_TLS_HANDSHAKE = Histogram(
    "probe_tls_handshake_seconds",
    "TLS handshake duration (DoH/DoT only)",
    ["resolver"]
)
PROBE_SUCCESS = Counter(
    "probe_success_total",
    "Successful query count",
    ["resolver", "protocol"]
)
PROBE_FAILURES = Counter(
    "probe_failures_total",
    "Failed query count with reason",
    ["resolver", "protocol", "reason"]
)
PROBE_CERT_EXPIRY = Gauge(
    "probe_cert_expiry_days",
    "Days until TLS certificate expires",
    ["resolver"]
)

# Load target configuration
TARGETS_FILE = os.getenv("TARGETS_FILE", "targets.json")

def load_targets(filepath: str) -> List[Dict[str, Any]]:
    """
    Loads measurement targets from a JSON file.

    Args:
        filepath (str): Path to the JSON configuration file.

    Returns:
        List[Dict[str, Any]]: A list of target configurations.
    """
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading targets from {filepath}: {e}")
        return []

async def measure_dns(ip: str, operator: Optional[str] = None) -> Dict[str, Any]:
    """
    Measures standard plaintext DNS query latency and status.

    Args:
        ip (str): IP address of the target resolver.
        operator (Optional[str]): Name of the DNS operator. Defaults to None.

    Returns:
        Dict[str, Any]: Dictionary containing measurement outcomes.
    """
    resolver = operator if operator is not None else ip
    result = {
        "resolver": resolver,
        "protocol": "DNS",
        "rtt_seconds": None,
        "success": False,
        "failure_reason": None
    }

    try:
        query = dns.message.make_query("google.com", dns.rdatatype.A)
        loop = asyncio.get_running_loop()
        start_time = time.perf_counter()
        await loop.run_in_executor(None, lambda: dns.query.udp(query, ip, timeout=5.0))
        result["rtt_seconds"] = time.perf_counter() - start_time
        result["success"] = True
    except Exception as e:
        result["success"] = False
        result["failure_reason"] = str(e)

    return result

async def measure_doh(endpoint: str, operator: str) -> Dict[str, Any]:
    """
    Measures DNS-over-HTTPS (DoH) query latency, TLS handshake, and certificate expiry.

    Args:
        endpoint (str): DoH HTTPS endpoint URL.
        operator (str): Name of the DNS operator.

    Returns:
        Dict[str, Any]: Dictionary containing measurement outcomes.
    """
    result = {
        "resolver": operator,
        "protocol": "DoH",
        "rtt_seconds": None,
        "tls_handshake_seconds": None,
        "success": False,
        "failure_reason": None,
        "cert_expiry_days": None
    }

    try:
        query = dns.message.make_query("google.com", dns.rdatatype.A)
        wire_data = query.to_wire()

        tls_start = time.perf_counter()
        # TODO: Extract cert info (cert_expiry_days) from the httpx response directly using the underlying transport
        async with httpx.AsyncClient(timeout=5.0, verify=True) as client:
            response = await client.post(
                endpoint,
                headers={
                    "Content-Type": "application/dns-message",
                    "Accept": "application/dns-message"
                },
                content=wire_data
            )
        
        total_time = time.perf_counter() - tls_start
        rtt_seconds = response.elapsed.total_seconds()
        tls_handshake_seconds = max(0.0, total_time - rtt_seconds)

        if response.status_code == 200:
            try:
                dns.message.from_wire(response.content)
                result["rtt_seconds"] = rtt_seconds
                result["tls_handshake_seconds"] = tls_handshake_seconds
                result["success"] = True
            except Exception as parse_err:
                result["success"] = False
                result["failure_reason"] = f"Invalid DNS wireformat: {parse_err}"
        else:
            result["success"] = False
            result["failure_reason"] = f"HTTP status code {response.status_code}"

    except Exception as e:
        result["success"] = False
        result["failure_reason"] = str(e)

    return result

async def measure_dot(host: str, operator: str) -> Dict[str, Any]:
    """
    Measures DNS-over-TLS (DoT) query latency, TLS handshake, and certificate expiry.

    Args:
        host (str): DoT host name and port (e.g., host:853).
        operator (str): Name of the DNS operator.

    Returns:
        Dict[str, Any]: Dictionary containing measurement outcomes.
    """
    result = {
        "resolver": operator,
        "protocol": "DoT",
        "rtt_seconds": None,
        "tls_handshake_seconds": None,
        "success": False,
        "failure_reason": None,
        "cert_expiry_days": None
    }

    try:
        if ":" in host:
            hostname, port_str = host.split(":", 1)
            port = int(port_str)
        else:
            hostname = host
            port = 853

        loop = asyncio.get_running_loop()

        def do_dot_query():
            context = ssl.create_default_context()
            
            def read_exactly(sslsock, n):
                data = b''
                while len(data) < n:
                    packet = sslsock.recv(n - len(data))
                    if not packet:
                        raise ConnectionError("Connection closed before reading complete data")
                    data += packet
                return data

            with socket.create_connection((hostname, port), timeout=5.0) as sock:
                start_handshake = time.perf_counter()
                with context.wrap_socket(sock, server_hostname=hostname) as sslsock:
                    tls_handshake = time.perf_counter() - start_handshake
                    cert = sslsock.getpeercert()

                    query = dns.message.make_query("google.com", dns.rdatatype.A)
                    wire_data = query.to_wire()
                    length_prefix = len(wire_data).to_bytes(2, byteorder='big')

                    start_query = time.perf_counter()
                    sslsock.sendall(length_prefix + wire_data)

                    response_len_bytes = read_exactly(sslsock, 2)
                    response_len = int.from_bytes(response_len_bytes, byteorder='big')
                    response_data = read_exactly(sslsock, response_len)
                    rtt = time.perf_counter() - start_query

                    dns.message.from_wire(response_data)

            return tls_handshake, cert, rtt

        tls_handshake_seconds, cert, rtt_seconds = await loop.run_in_executor(None, do_dot_query)

        result["tls_handshake_seconds"] = tls_handshake_seconds
        result["rtt_seconds"] = rtt_seconds
        result["success"] = True

        if cert and 'notAfter' in cert:
            expiry_str = cert['notAfter']
            expiry_dt = datetime.strptime(expiry_str, "%b %d %H:%M:%S %Y %Z")
            delta = expiry_dt - datetime.utcnow()
            result["cert_expiry_days"] = delta.days

    except Exception as e:
        result["success"] = False
        result["failure_reason"] = str(e)

    return result

async def run_measurement_cycle(db: Session) -> None:
    """
    Runs a single cycle of measurements for all configured targets.

    Args:
        db (Session): SQLAlchemy database session to save telemetry.
    """
    targets = load_targets(TARGETS_FILE)
    if not targets:
        return

    tasks = []
    for target in targets:
        ip = target.get("ip")
        operator = target.get("operator")
        doh_endpoint = target.get("doh_endpoint")
        dot_host = target.get("dot_host")

        if ip:
            tasks.append(measure_dns(ip, operator))
        if doh_endpoint and operator:
            tasks.append(measure_doh(doh_endpoint, operator))
        if dot_host and operator:
            tasks.append(measure_dot(dot_host, operator))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, Exception):
            print(f"Measurement task failed with exception: {result}")
            continue

        resolver = result.get("resolver")
        protocol = result.get("protocol")
        success = result.get("success", False)
        rtt_seconds = result.get("rtt_seconds")
        tls_handshake_seconds = result.get("tls_handshake_seconds")
        cert_expiry_days = result.get("cert_expiry_days")
        failure_reason = result.get("failure_reason")

        if success:
            PROBE_SUCCESS.labels(resolver=resolver, protocol=protocol).inc()
            if rtt_seconds is not None:
                PROBE_RTT.labels(resolver=resolver, protocol=protocol).observe(rtt_seconds)
            if tls_handshake_seconds is not None:
                PROBE_TLS_HANDSHAKE.labels(resolver=resolver).observe(tls_handshake_seconds)
            if cert_expiry_days is not None:
                PROBE_CERT_EXPIRY.labels(resolver=resolver).set(cert_expiry_days)
        else:
            reason = failure_reason or "unknown"
            PROBE_FAILURES.labels(resolver=resolver, protocol=protocol, reason=reason).inc()

        db_record = DNSMeasurement(
            resolver=resolver,
            protocol=protocol,
            rtt_seconds=rtt_seconds,
            tls_handshake_seconds=tls_handshake_seconds,
            success=success,
            failure_reason=failure_reason,
            cert_expiry_days=cert_expiry_days,
            timestamp=datetime.utcnow()
        )
        db.add(db_record)

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Failed to commit measurement cycle to database: {e}")

async def measurement_loop() -> None:
    """
    Infinite loop to periodically execute measurement cycles.
    """
    while True:
        try:
            db = SessionLocal()
            try:
                await run_measurement_cycle(db)
            finally:
                db.close()
        except Exception as e:
            print(f"Error in measurement_loop cycle: {e}")
        
        await asyncio.sleep(30)

@app.get("/health")
def health_check() -> Dict[str, str]:
    """
    Simple health check endpoint.

    Returns:
        Dict[str, str]: Service status dict.
    """
    return {"status": "healthy"}

@app.post("/ingest")
def ingest_telemetry(measurement: Dict[str, Any], db: Session = Depends(get_db)) -> Dict[str, str]:
    """
    Ingest endpoint to receive measurement telemetry externally.

    Args:
        measurement (Dict[str, Any]): Telemetry payload.
        db (Session): SQLAlchemy database session.

    Returns:
        Dict[str, str]: Ingestion status dict.
    """
    timestamp = measurement.get("timestamp")
    if timestamp:
        try:
            if isinstance(timestamp, str):
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            else:
                dt = timestamp
        except Exception:
            dt = datetime.utcnow()
    else:
        dt = datetime.utcnow()

    db_record = DNSMeasurement(
        resolver=measurement.get("resolver"),
        protocol=measurement.get("protocol"),
        rtt_seconds=measurement.get("rtt_seconds"),
        tls_handshake_seconds=measurement.get("tls_handshake_seconds"),
        success=measurement.get("success", False),
        failure_reason=measurement.get("failure_reason"),
        cert_expiry_days=measurement.get("cert_expiry_days"),
        timestamp=dt
    )
    db.add(db_record)
    db.commit()
    return {"status": "success"}

@app.get("/metrics")
def metrics() -> Response:
    """
    Exposes Prometheus metrics for scraping.

    Returns:
        Response: Plain text response containing Prometheus metrics.
    """
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

if __name__ == "__main__":
    import uvicorn
    host = os.getenv("PROBE_HOST", "0.0.0.0")
    port = int(os.getenv("PROBE_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
