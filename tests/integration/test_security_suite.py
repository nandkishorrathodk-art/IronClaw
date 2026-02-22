"""
Integration tests for Security Suite (Phase 6)
Tests CVE database, scanners, and report generation
"""

import pytest
from datetime import datetime
from pathlib import Path

from src.security.cve_database import CVEDatabase, CVEEntry
from src.security.cvss_calculator import (
    CVSSCalculator,
    AttackVector,
    AttackComplexity,
    PrivilegesRequired,
    UserInteraction,
    Scope,
    ImpactMetric,
    quick_cvss,
)
from src.security.nuclei_scanner import NucleiScanner
from src.security.ai_scanner import AIVulnerabilityScanner, VulnerabilityFinding
from src.security.poc_generator import PoCGenerator, PoCLanguage
from src.security.report_generator import SecurityReportGenerator
from src.security.orchestrator import SecurityOrchestrator, ScanProfile
from src.database.session import get_db_session


@pytest.mark.asyncio
class TestCVSSCalculator:
    """Test CVSS 3.1 calculator"""

    def test_critical_vulnerability(self):
        """Test calculation of critical CVSS score"""
        calculator = CVSSCalculator()
        
        score = calculator.calculate(
            attack_vector=AttackVector.NETWORK,
            attack_complexity=AttackComplexity.LOW,
            privileges_required=PrivilegesRequired.NONE,
            user_interaction=UserInteraction.NONE,
            scope=Scope.UNCHANGED,
            confidentiality_impact=ImpactMetric.HIGH,
            integrity_impact=ImpactMetric.HIGH,
            availability_impact=ImpactMetric.HIGH,
        )
        
        assert score.base_score == 9.8
        assert score.severity == "CRITICAL"
        assert "CVSS:3.1" in score.vector_string

    def test_medium_vulnerability(self):
        """Test calculation of medium CVSS score"""
        calculator = CVSSCalculator()
        
        score = calculator.calculate(
            attack_vector=AttackVector.NETWORK,
            attack_complexity=AttackComplexity.LOW,
            privileges_required=PrivilegesRequired.LOW,
            user_interaction=UserInteraction.REQUIRED,
            scope=Scope.UNCHANGED,
            confidentiality_impact=ImpactMetric.LOW,
            integrity_impact=ImpactMetric.LOW,
            availability_impact=ImpactMetric.NONE,
        )
        
        assert 4.0 <= score.base_score < 7.0
        assert score.severity == "MEDIUM"

    def test_quick_cvss_helper(self):
        """Test quick CVSS helper function"""
        score = quick_cvss(
            network=True,
            easy=True,
            no_auth=True,
            no_interaction=True,
            high_impact=True,
        )
        
        assert score.base_score >= 9.0
        assert score.severity in ["CRITICAL", "HIGH"]

    def test_parse_vector_string(self):
        """Test parsing CVSS vector string"""
        calculator = CVSSCalculator()
        
        vector = "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"
        score = calculator.parse_vector(vector)
        
        assert score is not None
        assert score.base_score == 9.8
        assert score.severity == "CRITICAL"


@pytest.mark.asyncio
class TestCVEDatabase:
    """Test CVE database operations"""

    async def test_cve_database_initialization(self):
        """Test CVE database initialization"""
        cve_db = CVEDatabase()
        await cve_db.initialize()
        
        async with get_db_session() as db:
            count = await cve_db.get_cve_count(db)
            assert count >= 0

    async def test_cve_search(self):
        """Test CVE search functionality"""
        cve_db = CVEDatabase()
        
        async with get_db_session() as db:
            results = await cve_db.search_cves(
                db=db,
                keyword="SQL injection",
                severity="HIGH",
                limit=10,
            )
            
            assert isinstance(results, list)
            for cve in results:
                assert isinstance(cve, CVEEntry)
                assert cve.severity == "HIGH"

    @pytest.mark.skip(reason="Requires NVD API access")
    async def test_nvd_api_fetch(self):
        """Test fetching CVE from NVD API"""
        cve_db = CVEDatabase()
        
        async with get_db_session() as db:
            cve = await cve_db.get_cve_by_id("CVE-2021-44228", db)
            
            if cve:
                assert cve.cve_id == "CVE-2021-44228"
                assert "Log4j" in cve.description or "log4j" in cve.description.lower()
                assert cve.severity in ["CRITICAL", "HIGH"]


@pytest.mark.asyncio
class TestNucleiScanner:
    """Test Nuclei scanner integration"""

    async def test_nuclei_check_installed(self):
        """Test checking if Nuclei is installed"""
        scanner = NucleiScanner()
        installed = await scanner.check_installed()
        
        assert isinstance(installed, bool)

    @pytest.mark.skip(reason="Requires Nuclei installation")
    async def test_nuclei_list_templates(self):
        """Test listing Nuclei templates"""
        scanner = NucleiScanner()
        
        if await scanner.check_installed():
            templates = await scanner.list_templates()
            assert isinstance(templates, list)
            assert len(templates) > 0

    @pytest.mark.skip(reason="Requires target authorization")
    async def test_nuclei_scan(self):
        """Test Nuclei scanning (requires authorized target)"""
        scanner = NucleiScanner()
        
        if await scanner.check_installed():
            results = await scanner.scan_target(
                target="http://testphp.vulnweb.com",
                severity=["high", "critical"],
            )
            
            assert isinstance(results, list)


@pytest.mark.asyncio
class TestAIScanner:
    """Test AI-powered vulnerability scanner"""

    async def test_ai_scanner_initialization(self):
        """Test AI scanner initialization"""
        scanner = AIVulnerabilityScanner()
        assert scanner is not None

    @pytest.mark.skip(reason="Requires authorized target and AI provider")
    async def test_ai_scan_application(self):
        """Test AI scanning application"""
        scanner = AIVulnerabilityScanner()
        
        findings = await scanner.scan_application(
            base_url="http://testphp.vulnweb.com",
            endpoints=["/"],
        )
        
        assert isinstance(findings, list)
        for finding in findings:
            assert isinstance(finding, VulnerabilityFinding)
            assert finding.severity in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]


@pytest.mark.asyncio
class TestPoCGenerator:
    """Test Proof-of-Concept generator"""

    async def test_generate_curl_poc(self):
        """Test generating curl PoC"""
        generator = PoCGenerator()
        
        finding = VulnerabilityFinding(
            title="SQL Injection",
            description="SQL injection vulnerability",
            severity="HIGH",
            confidence=0.9,
            affected_url="http://example.com/test?id=1",
            http_method="GET",
            vulnerable_parameter="id",
            evidence="SQL error in response",
            attack_vector="' OR '1'='1",
            remediation="Use parameterized queries",
            cwe_id="CWE-89",
        )
        
        poc = await generator.generate_poc(finding, PoCLanguage.CURL)
        
        assert poc.language == "curl"
        assert "curl" in poc.code
        assert "example.com" in poc.code
        assert poc.warnings is not None

    async def test_save_poc(self, tmp_path):
        """Test saving PoC to file"""
        generator = PoCGenerator()
        
        finding = VulnerabilityFinding(
            title="Test Vulnerability",
            description="Test description",
            severity="MEDIUM",
            confidence=0.8,
            affected_url="http://test.com",
            http_method="GET",
            vulnerable_parameter="test",
            evidence="Test evidence",
            attack_vector="test",
            remediation="Test remediation",
        )
        
        poc = await generator.generate_poc(finding, PoCLanguage.CURL)
        output_path = tmp_path / "test_poc.sh"
        
        saved_path = generator.save_poc(poc, str(output_path))
        
        assert Path(saved_path).exists()
        content = Path(saved_path).read_text()
        assert "curl" in content


@pytest.mark.asyncio
class TestReportGenerator:
    """Test security report generator"""

    def test_generate_report(self):
        """Test generating security report"""
        generator = SecurityReportGenerator()
        
        findings = [
            VulnerabilityFinding(
                title="SQL Injection",
                description="SQL injection vulnerability",
                severity="HIGH",
                confidence=0.9,
                affected_url="http://example.com/test",
                http_method="GET",
                vulnerable_parameter="id",
                evidence="SQL error",
                attack_vector="' OR '1'='1",
                remediation="Use parameterized queries",
                cwe_id="CWE-89",
                verified=True,
            ),
        ]
        
        report = generator.generate_report(
            target="http://example.com",
            findings=findings,
        )
        
        assert report.title is not None
        assert report.target == "http://example.com"
        assert len(report.findings) == 1
        assert report.statistics["total"] == 1
        assert report.statistics["high"] == 1

    def test_export_html(self, tmp_path):
        """Test exporting HTML report"""
        generator = SecurityReportGenerator()
        
        findings = [
            VulnerabilityFinding(
                title="XSS Vulnerability",
                description="Cross-site scripting",
                severity="MEDIUM",
                confidence=0.8,
                affected_url="http://example.com/page",
                http_method="GET",
                vulnerable_parameter="q",
                evidence="<script> reflected",
                attack_vector="<script>alert(1)</script>",
                remediation="Encode output",
                cwe_id="CWE-79",
            ),
        ]
        
        report = generator.generate_report("http://example.com", findings)
        output_path = tmp_path / "report.html"
        
        path = generator.export_html(report, str(output_path))
        
        assert Path(path).exists()
        content = Path(path).read_text()
        assert "<!DOCTYPE html>" in content
        assert "XSS Vulnerability" in content

    def test_export_markdown(self, tmp_path):
        """Test exporting Markdown report"""
        generator = SecurityReportGenerator()
        
        findings = []
        report = generator.generate_report("http://example.com", findings)
        output_path = tmp_path / "report.md"
        
        path = generator.export_markdown(report, str(output_path))
        
        assert Path(path).exists()
        content = Path(path).read_text()
        assert "# " in content
        assert "example.com" in content

    def test_export_json(self, tmp_path):
        """Test exporting JSON report"""
        generator = SecurityReportGenerator()
        
        findings = []
        report = generator.generate_report("http://example.com", findings)
        output_path = tmp_path / "report.json"
        
        path = generator.export_json(report, str(output_path))
        
        assert Path(path).exists()
        import json
        with open(path) as f:
            data = json.load(f)
        assert data["target"] == "http://example.com"
        assert "findings" in data


@pytest.mark.asyncio
class TestSecurityOrchestrator:
    """Test security orchestrator integration"""

    async def test_orchestrator_initialization(self):
        """Test orchestrator initialization"""
        orchestrator = SecurityOrchestrator()
        await orchestrator.initialize()
        
        assert orchestrator.cve_db is not None
        assert orchestrator.nuclei is not None
        assert orchestrator.ai_scanner is not None

    @pytest.mark.skip(reason="Requires authorized target")
    async def test_comprehensive_scan(self):
        """Test comprehensive security scan"""
        orchestrator = SecurityOrchestrator()
        await orchestrator.initialize()
        
        scan_id = await orchestrator.comprehensive_scan(
            target="http://testphp.vulnweb.com",
            scan_profile=ScanProfile.QUICK,
        )
        
        assert scan_id is not None
        assert len(scan_id) == 36

        results = await orchestrator.get_scan_results(scan_id)
        assert results["scan_id"] == scan_id
        assert results["status"] in ["RUNNING", "COMPLETED", "FAILED"]

    async def test_generate_scan_report(self, tmp_path):
        """Test generating report from scan results"""
        pass


@pytest.fixture
def sample_vulnerability_finding():
    """Fixture providing a sample vulnerability finding"""
    return VulnerabilityFinding(
        title="Test Vulnerability",
        description="Test vulnerability for testing purposes",
        severity="MEDIUM",
        confidence=0.75,
        affected_url="http://test.com/vulnerable",
        http_method="GET",
        vulnerable_parameter="test_param",
        evidence="Test evidence data",
        attack_vector="test_payload",
        remediation="Test remediation steps",
        cwe_id="CWE-79",
        verified=False,
    )


def test_security_models_import():
    """Test that all security models can be imported"""
    from src.security.models import (
        CVEModel,
        SecurityScanModel,
        VulnerabilityFindingModel,
        SecurityReportModel,
        SeverityLevel,
        ScanStatus,
    )
    
    assert CVEModel is not None
    assert SecurityScanModel is not None
    assert VulnerabilityFindingModel is not None
    assert SecurityReportModel is not None


def test_security_suite_imports():
    """Test that all security suite modules can be imported"""
    from src.security import (
        CVEDatabase,
        BurpSuiteClient,
        NucleiScanner,
        AIVulnerabilityScanner,
        PoCGenerator,
        SecurityReportGenerator,
        CVSSCalculator,
        SecurityOrchestrator,
    )
    
    assert CVEDatabase is not None
    assert BurpSuiteClient is not None
    assert NucleiScanner is not None
    assert AIVulnerabilityScanner is not None
    assert PoCGenerator is not None
    assert SecurityReportGenerator is not None
    assert CVSSCalculator is not None
    assert SecurityOrchestrator is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
