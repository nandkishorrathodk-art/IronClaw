"""
Database models for security suite
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import relationship
from src.database.base import Base


class SeverityLevel(str, Enum):
    """CVE severity levels"""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NONE"


class ScanStatus(str, Enum):
    """Security scan status"""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class CVEModel(Base):
    """CVE vulnerability records"""

    __tablename__ = "cves"

    id = Column(Integer, primary_key=True, index=True)
    cve_id = Column(String(20), unique=True, nullable=False, index=True)
    published_date = Column(DateTime, nullable=False, index=True)
    last_modified_date = Column(DateTime, nullable=False)
    description = Column(Text, nullable=False)
    cvss_score = Column(Float, nullable=True, index=True)
    cvss_vector = Column(String(100), nullable=True)
    cvss_version = Column(String(10), nullable=True)
    severity = Column(String(20), nullable=False, index=True)
    cpe_matches = Column(JSON, nullable=True)
    references = Column(JSON, nullable=True)
    exploit_available = Column(Integer, default=0)
    metasploit_module = Column(String(200), nullable=True)
    exploitdb_id = Column(String(20), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    scans = relationship("SecurityScanModel", back_populates="cve_findings")


class SecurityScanModel(Base):
    """Security scan records"""

    __tablename__ = "security_scans"

    id = Column(Integer, primary_key=True, index=True)
    scan_id = Column(String(36), unique=True, nullable=False, index=True)
    target_url = Column(String(500), nullable=False)
    scan_type = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False, default=ScanStatus.QUEUED.value)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    findings_count = Column(Integer, default=0)
    critical_count = Column(Integer, default=0)
    high_count = Column(Integer, default=0)
    medium_count = Column(Integer, default=0)
    low_count = Column(Integer, default=0)
    scanner_name = Column(String(50), nullable=False)
    scanner_version = Column(String(20), nullable=True)
    raw_results = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # User who initiated the scan
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Relationships
    findings = relationship("VulnerabilityFindingModel", back_populates="scan")
    cve_findings = relationship("CVEModel", back_populates="scans")


class VulnerabilityFindingModel(Base):
    """Individual vulnerability findings"""

    __tablename__ = "vulnerability_findings"

    id = Column(Integer, primary_key=True, index=True)
    scan_id = Column(Integer, ForeignKey("security_scans.id"), nullable=False)
    finding_id = Column(String(36), unique=True, nullable=False, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=False)
    severity = Column(String(20), nullable=False, index=True)
    cvss_score = Column(Float, nullable=True)
    cvss_vector = Column(String(100), nullable=True)
    cve_id = Column(String(20), nullable=True, index=True)
    cwe_id = Column(String(20), nullable=True)
    affected_url = Column(String(1000), nullable=False)
    http_method = Column(String(10), nullable=True)
    vulnerable_parameter = Column(String(200), nullable=True)
    evidence = Column(Text, nullable=True)
    remediation = Column(Text, nullable=True)
    references = Column(JSON, nullable=True)
    false_positive = Column(Integer, default=0)
    verified_by_ai = Column(Integer, default=0)
    ai_confidence = Column(Float, nullable=True)
    proof_of_concept = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    scan = relationship("SecurityScanModel", back_populates="findings")


class SecurityReportModel(Base):
    """Security assessment reports"""

    __tablename__ = "security_reports"

    id = Column(Integer, primary_key=True, index=True)
    report_id = Column(String(36), unique=True, nullable=False, index=True)
    scan_id = Column(Integer, ForeignKey("security_scans.id"), nullable=False)
    report_type = Column(String(50), nullable=False)
    title = Column(String(500), nullable=False)
    executive_summary = Column(Text, nullable=True)
    generated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    file_path = Column(String(1000), nullable=True)
    file_format = Column(String(20), nullable=False)
    file_size_bytes = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
