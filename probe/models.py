"""
Database models for Chronos-DNS probe telemetry.
Defines the schema for storing DNS, DoH, and DoT measurement results.
"""

import os
from datetime import datetime
from typing import Generator

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

# Database URL retrieved from environment variable
# Defaults to a local sqlite database for development if not provided
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///chronos_dns.db")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""
    pass

class DNSMeasurement(Base):
    """
    SQLAlchemy model representing a single DNS-over-Encryption measurement.
    """
    __tablename__ = "dns_measurements"

    id = Column(Integer, primary_key=True, index=True)
    resolver = Column(String, nullable=False, index=True)
    protocol = Column(String, nullable=False, index=True)  # "DNS", "DoH", "DoT"
    rtt_seconds = Column(Float, nullable=True)
    tls_handshake_seconds = Column(Float, nullable=True)
    success = Column(Boolean, nullable=False)
    failure_reason = Column(String, nullable=True)
    cert_expiry_days = Column(Integer, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

def init_db() -> None:
    """
    Initializes the database schema.
    Creates all tables defined by the models if they don't exist.
    """
    Base.metadata.create_all(bind=engine)

def get_db() -> Generator[Session, None, None]:
    """
    Dependency to get a database session.
    Yields:
        Generator[Session, None, None]: SQLAlchemy database session.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
