"""
Unit and integration tests for the Chronos-DNS probe.
"""

import pytest
import tempfile
import os
import json
import shutil
import httpx
import socket
import ssl
from unittest.mock import patch, MagicMock, AsyncMock

import dns.message
import dns.rdatatype
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from probe import app, load_targets, measure_dns, measure_doh, measure_dot
from models import Base, get_db, DNSMeasurement

# Setup a clean database for testing in a temporary directory
temp_dir = tempfile.mkdtemp()
TEST_DATABASE_URL = f"sqlite:///{os.path.join(temp_dir, 'test_chronos.db')}"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="session", autouse=True)
def cleanup_temp_dir():
    """
    Cleans up the temporary directory containing the test database after the test session ends.
    """
    yield
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)

@pytest.fixture(scope="function")
def db_session():
    """
    Fixture that provisions a clean SQLite database for each test function.
    """
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def client(db_session):
    """
    Fixture that overrides FastAPI db dependency and provides a TestClient.
    """
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

def test_health_check(client) -> None:
    """
    Tests the health check endpoint returns 200 and success status.
    """
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

def test_load_targets() -> None:
    """
    Tests loading resolver targets from targets.json.
    """
    targets_data = [
        {
            "ip": "1.1.1.1",
            "operator": "Cloudflare",
            "doh_endpoint": "https://cloudflare-dns.com/dns-query",
            "dot_host": "one.one.one.one:853"
        }
    ]
    with tempfile.NamedTemporaryFile(mode="w+", suffix=".json", delete=False) as tmp:
        json.dump(targets_data, tmp)
        tmp_path = tmp.name

    try:
        loaded = load_targets(tmp_path)
        assert len(loaded) == 1
        assert loaded[0]["operator"] == "Cloudflare"
        assert loaded[0]["ip"] == "1.1.1.1"
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def test_metrics_endpoint(client) -> None:
    """
    Tests that the Prometheus metrics endpoint returns successfully.
    """
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")

def test_ingest_telemetry(client, db_session) -> None:
    """
    Tests the ingestion API endpoint.
    """
    payload = {
        "resolver": "Google",
        "protocol": "DoH",
        "rtt_seconds": 0.123,
        "tls_handshake_seconds": 0.045,
        "success": True,
        "failure_reason": None,
        "cert_expiry_days": 89,
        "timestamp": "2026-06-16T08:00:00Z"
    }
    response = client.post("/ingest", json=payload)
    assert response.status_code == 200
    assert response.json() == {"status": "success"}

    # Verify the record exists in the test database
    record = db_session.query(DNSMeasurement).filter_by(resolver="Google", protocol="DoH").first()
    assert record is not None
    assert record.rtt_seconds == 0.123
    assert record.success is True
    assert record.cert_expiry_days == 89

@pytest.mark.asyncio
async def test_measure_dns() -> None:
    """
    Tests the measure_dns helper function stub.
    """
    mock_msg = MagicMock()
    with patch("dns.query.udp", return_value=mock_msg) as mock_udp:
        res = await measure_dns("8.8.8.8", "Google")
        assert res["success"] is True
        assert isinstance(res["rtt_seconds"], float)
        assert res["resolver"] == "Google"
        assert res["protocol"] == "DNS"
        mock_udp.assert_called_once()

@pytest.mark.asyncio
async def test_measure_doh() -> None:
    """
    Tests the measure_doh helper function stub.
    """
    query_msg = dns.message.make_query("google.com", dns.rdatatype.A)
    dummy_wire = query_msg.to_wire()

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.content = dummy_wire
    mock_resp.elapsed = MagicMock()
    mock_resp.elapsed.total_seconds.return_value = 0.05

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        
        res = await measure_doh("https://dns.google/dns-query", "Google")
        assert res["success"] is True
        assert res["resolver"] == "Google"
        assert res["protocol"] == "DoH"
        assert isinstance(res["tls_handshake_seconds"], float)
        assert res["rtt_seconds"] == 0.05

@pytest.mark.asyncio
async def test_measure_dot() -> None:
    """
    Tests the measure_dot helper function stub.
    """
    query_msg = dns.message.make_query("google.com", dns.rdatatype.A)
    dummy_wire = query_msg.to_wire()
    length_prefix = len(dummy_wire).to_bytes(2, byteorder='big')
    full_response = length_prefix + dummy_wire

    mock_sslsock = MagicMock()
    mock_sslsock.getpeercert.return_value = {
        'notAfter': 'Nov 24 12:00:00 2026 GMT'
    }

    # Mock recv behavior for read_exactly to stream response data
    response_stream = [full_response[0:2], full_response[2:]]
    stream_idx = 0

    def mock_recv(n):
        nonlocal stream_idx
        if stream_idx >= len(response_stream):
            return b''
        chunk = response_stream[stream_idx]
        stream_idx += 1
        return chunk

    mock_sslsock.recv.side_effect = mock_recv

    mock_context = MagicMock()
    mock_context.wrap_socket.return_value.__enter__.return_value = mock_sslsock

    mock_sock = MagicMock()

    with patch("socket.create_connection") as mock_connect, \
         patch("ssl.create_default_context", return_value=mock_context):
        
        mock_connect.return_value.__enter__.return_value = mock_sock
        
        res = await measure_dot("dns.google:853", "Google")
        
        assert res["success"] is True
        assert res["resolver"] == "Google"
        assert res["protocol"] == "DoT"
        assert isinstance(res["rtt_seconds"], float)
        assert isinstance(res["tls_handshake_seconds"], float)
        assert res["cert_expiry_days"] is not None
