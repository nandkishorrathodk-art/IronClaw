"""
Security Orchestrator - Unified Interface for All Security Tools
Coordinates CVE database, scanners, and report generation
"""

import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.session import get_db_session
from src.security.ai_scanner import AIVulnerabilityScanner, VulnerabilityFinding
from src.security.burp_client import BurpSuiteClient
from src.security.cve_database import CVEDatabase
from src.security.models import SecurityScanModel, VulnerabilityFindingModel, ScanStatus
from src.security.nuclei_scanner import NucleiScanner
from src.security.poc_generator import PoCGenerator, PoCLanguage
from src.security.report_generator import SecurityReportGenerator


class ScanProfile(str, Enum):
    """Predefined scan profiles"""
    QUICK = "quick"
    STANDARD = "standard"
    FULL = "full"
    DEEP = "deep"


class SecurityOrchestrator:
    """
    Security suite orchestrator
    
    Provides unified interface for:
    - CVE database queries
    - Vulnerability scanning (Burp, Nuclei, AI)
    - PoC generation
    - Professional report generation
    - Scan orchestration and tracking
    """

    def __init__(
        self,
        burp_url: Optional[str] = None,
        burp_api_key: Optional[str] = None,
    ):
        """
        Initialize security orchestrator
        
        Args:
            burp_url: Burp Suite API URL
            burp_api_key: Burp Suite API key
        """
        self.cve_db = CVEDatabase()
        self.nuclei = NucleiScanner()
        self.ai_scanner = AIVulnerabilityScanner()
        self.poc_gen = PoCGenerator()
        self.report_gen = SecurityReportGenerator()
        self.burp_url = burp_url
        self.burp_api_key = burp_api_key

    async def initialize(self) -> None:
        """Initialize all components"""
        logger.info("Initializing Security Orchestrator...")
        await self.cve_db.initialize()
        await self.nuclei.check_installed()
        logger.info("Security Orchestrator ready")

    async def comprehensive_scan(
        self,
        target: str,
        scan_profile: ScanProfile = ScanProfile.STANDARD,
        user_id: Optional[int] = None,
    ) -> str:
        """
        Run comprehensive security scan
        
        Args:
            target: Target URL to scan
            scan_profile: Scan intensity level
            user_id: User initiating the scan
        
        Returns:
            Scan ID for tracking
        """
        scan_id = str(uuid.uuid4())
        logger.info(f"Starting comprehensive scan {scan_id} on {target}")

        async with get_db_session() as db:
            scan_model = SecurityScanModel(
                scan_id=scan_id,
                target_url=target,
                scan_type=scan_profile.value,
                status=ScanStatus.RUNNING.value,
                started_at=datetime.utcnow(),
                scanner_name="comprehensive",
                user_id=user_id,
            )
            db.add(scan_model)
            await db.commit()

        findings: List[VulnerabilityFinding] = []

        try:
            if scan_profile in [ScanProfile.STANDARD, ScanProfile.FULL, ScanProfile.DEEP]:
                logger.info(f"Running Nuclei scan on {target}")
                nuclei_results = await self.nuclei.scan_target(
                    target=target,
                    severity=["critical", "high", "medium"] if scan_profile != ScanProfile.DEEP else None,
                )
                
                for result in nuclei_results:
                    finding = VulnerabilityFinding(
                        title=result.template_name,
                        description=result.description or "Detected by Nuclei template",
                        severity=result.severity,
                        confidence=0.8,
                        affected_url=result.matched_at,
                        http_method="UNKNOWN",
                        vulnerable_parameter=None,
                        evidence=result.matcher_name or "Template matched",
                        attack_vector=result.template_id,
                        remediation="Review Nuclei template documentation",
                        cwe_id=result.cve_id,
                        verified=True,
                    )
                    findings.append(finding)

            if scan_profile in [ScanProfile.FULL, ScanProfile.DEEP]:
                logger.info(f"Running AI vulnerability scan on {target}")
                endpoints = ["/", "/api", "/admin", "/login"]
                ai_findings = await self.ai_scanner.scan_application(
                    base_url=target,
                    endpoints=endpoints,
                )
                findings.extend(ai_findings)

            if scan_profile == ScanProfile.DEEP and self.burp_url:
                logger.info(f"Running Burp Suite scan on {target}")
                async with BurpSuiteClient(self.burp_url, self.burp_api_key) as burp:
                    burp_scan_id = await burp.start_scan(target)
                    burp_scan = await burp.wait_for_scan(
                        burp_scan_id,
                        poll_interval=30,
                        max_wait=1800,
                    )
                    
                    if burp_scan.status == "succeeded":
                        burp_issues = await burp.get_scan_issues(burp_scan_id)
                        
                        for issue in burp_issues:
                            finding = VulnerabilityFinding(
                                title=issue.name,
                                description=f"Burp Suite: {issue.issue_type}",
                                severity=issue.severity.upper(),
                                confidence=0.9 if issue.confidence == "certain" else 0.7,
                                affected_url=issue.path,
                                http_method="UNKNOWN",
                                vulnerable_parameter=None,
                                evidence=issue.evidence or "Detected by Burp Suite",
                                attack_vector="burp_" + issue.issue_type,
                                remediation=issue.remediation or "Review Burp Suite issue details",
                                verified=True,
                            )
                            findings.append(finding)

            async with get_db_session() as db:
                result = await db.execute(
                    select(SecurityScanModel).where(SecurityScanModel.scan_id == scan_id)
                )
                scan_model = result.scalar_one()
                
                scan_model.status = ScanStatus.COMPLETED.value
                scan_model.completed_at = datetime.utcnow()
                scan_model.duration_seconds = int(
                    (scan_model.completed_at - scan_model.started_at).total_seconds()
                )
                scan_model.findings_count = len(findings)
                
                for severity in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
                    count = sum(1 for f in findings if f.severity == severity)
                    setattr(scan_model, f"{severity.lower()}_count", count)
                
                for finding in findings:
                    finding_model = VulnerabilityFindingModel(
                        scan_id=scan_model.id,
                        finding_id=str(uuid.uuid4()),
                        title=finding.title,
                        description=finding.description,
                        severity=finding.severity,
                        cvss_score=None,
                        cve_id=finding.cwe_id,
                        affected_url=finding.affected_url,
                        http_method=finding.http_method,
                        vulnerable_parameter=finding.vulnerable_parameter,
                        evidence=finding.evidence,
                        remediation=finding.remediation,
                        verified_by_ai=1 if finding.verified else 0,
                        ai_confidence=finding.confidence,
                    )
                    db.add(finding_model)
                
                await db.commit()

            logger.info(
                f"Scan {scan_id} completed: {len(findings)} findings "
                f"({scan_model.critical_count} critical, {scan_model.high_count} high)"
            )

        except Exception as e:
            logger.error(f"Error during scan {scan_id}: {e}")
            
            async with get_db_session() as db:
                result = await db.execute(
                    select(SecurityScanModel).where(SecurityScanModel.scan_id == scan_id)
                )
                scan_model = result.scalar_one()
                scan_model.status = ScanStatus.FAILED.value
                scan_model.error_message = str(e)
                await db.commit()

        return scan_id

    async def get_scan_results(self, scan_id: str) -> Dict:
        """
        Get scan results and findings
        
        Args:
            scan_id: Scan identifier
        
        Returns:
            Dictionary with scan info and findings
        """
        async with get_db_session() as db:
            result = await db.execute(
                select(SecurityScanModel).where(SecurityScanModel.scan_id == scan_id)
            )
            scan = result.scalar_one_or_none()
            
            if not scan:
                raise ValueError(f"Scan {scan_id} not found")
            
            findings_result = await db.execute(
                select(VulnerabilityFindingModel).where(
                    VulnerabilityFindingModel.scan_id == scan.id
                )
            )
            findings = findings_result.scalars().all()
            
            return {
                "scan_id": scan.scan_id,
                "target": scan.target_url,
                "status": scan.status,
                "started_at": scan.started_at.isoformat() if scan.started_at else None,
                "completed_at": scan.completed_at.isoformat() if scan.completed_at else None,
                "duration_seconds": scan.duration_seconds,
                "findings_count": scan.findings_count,
                "critical": scan.critical_count,
                "high": scan.high_count,
                "medium": scan.medium_count,
                "low": scan.low_count,
                "findings": [
                    {
                        "finding_id": f.finding_id,
                        "title": f.title,
                        "description": f.description,
                        "severity": f.severity,
                        "url": f.affected_url,
                        "parameter": f.vulnerable_parameter,
                        "evidence": f.evidence,
                        "remediation": f.remediation,
                        "verified": bool(f.verified_by_ai),
                        "confidence": f.ai_confidence,
                    }
                    for f in findings
                ],
            }

    async def generate_scan_report(
        self,
        scan_id: str,
        output_format: str = "html",
        output_dir: Optional[str] = None,
    ) -> str:
        """
        Generate report for completed scan
        
        Args:
            scan_id: Scan identifier
            output_format: Report format (html, markdown, json)
            output_dir: Output directory
        
        Returns:
            Path to generated report
        """
        results = await self.get_scan_results(scan_id)
        
        findings = [
            VulnerabilityFinding(
                title=f["title"],
                description=f["description"],
                severity=f["severity"],
                confidence=f["confidence"] or 0.5,
                affected_url=f["url"],
                http_method="UNKNOWN",
                vulnerable_parameter=f["parameter"],
                evidence=f["evidence"],
                attack_vector="",
                remediation=f["remediation"],
                verified=f["verified"],
            )
            for f in results["findings"]
        ]
        
        report = self.report_gen.generate_report(
            target=results["target"],
            findings=findings,
            scan_date=datetime.fromisoformat(results["started_at"]),
        )
        
        output_dir = Path(output_dir) if output_dir else self.report_gen.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        
        filename = f"security_report_{scan_id}.{output_format}"
        output_path = str(output_dir / filename)
        
        if output_format == "html":
            path = self.report_gen.export_html(report, output_path)
        elif output_format == "markdown":
            path = self.report_gen.export_markdown(report, output_path)
        elif output_format == "json":
            path = self.report_gen.export_json(report, output_path)
        else:
            raise ValueError(f"Unsupported format: {output_format}")
        
        logger.info(f"Generated {output_format} report: {path}")
        return path

    async def generate_poc_for_finding(
        self,
        finding_id: str,
        language: PoCLanguage = PoCLanguage.PYTHON,
        output_dir: Optional[str] = None,
    ) -> str:
        """
        Generate PoC script for a finding
        
        Args:
            finding_id: Finding identifier
            language: PoC language
            output_dir: Output directory
        
        Returns:
            Path to generated PoC script
        """
        async with get_db_session() as db:
            result = await db.execute(
                select(VulnerabilityFindingModel).where(
                    VulnerabilityFindingModel.finding_id == finding_id
                )
            )
            finding_model = result.scalar_one_or_none()
            
            if not finding_model:
                raise ValueError(f"Finding {finding_id} not found")
            
            finding = VulnerabilityFinding(
                title=finding_model.title,
                description=finding_model.description,
                severity=finding_model.severity,
                confidence=finding_model.ai_confidence or 0.5,
                affected_url=finding_model.affected_url,
                http_method=finding_model.http_method or "GET",
                vulnerable_parameter=finding_model.vulnerable_parameter,
                evidence=finding_model.evidence,
                attack_vector="",
                remediation=finding_model.remediation,
                cwe_id=finding_model.cve_id,
                verified=bool(finding_model.verified_by_ai),
            )
        
        poc = await self.poc_gen.generate_poc(finding, language)
        
        output_dir = Path(output_dir) if output_dir else Path("data/pocs")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        filename = f"poc_{finding_id}{'.py' if language == PoCLanguage.PYTHON else '.sh'}"
        output_path = str(output_dir / filename)
        
        path = self.poc_gen.save_poc(poc, output_path)
        return path


orchestrator = SecurityOrchestrator()
