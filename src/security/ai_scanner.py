"""
AI-Powered Vulnerability Scanner
Uses LLM to analyze HTTP requests/responses and detect vulnerabilities
"""

import asyncio
from dataclasses import dataclass
from typing import Dict, List, Optional
from urllib.parse import urlparse

import aiohttp
from loguru import logger

from src.cognitive.llm.router import AIRouter


@dataclass
class VulnerabilityFinding:
    """AI-detected vulnerability"""
    title: str
    description: str
    severity: str
    confidence: float
    affected_url: str
    http_method: str
    vulnerable_parameter: Optional[str]
    evidence: str
    attack_vector: str
    remediation: str
    cwe_id: Optional[str] = None
    verified: bool = False


class AIVulnerabilityScanner:
    """
    AI-powered vulnerability detection
    
    Features:
    - Pattern-based detection (SQL injection, XSS, etc.)
    - LLM verification of findings
    - False positive filtering
    - Context-aware analysis
    - Behavioral vulnerability detection
    """

    VULNERABILITY_PATTERNS = {
        "sqli": [
            r"SQL syntax.*error",
            r"mysql_fetch",
            r"ORA-\d+",
            r"Microsoft.*ODBC",
            r"PostgreSQL.*ERROR",
        ],
        "xss": [
            r"<script[^>]*>",
            r"javascript:",
            r"onerror\s*=",
            r"onload\s*=",
        ],
        "path_traversal": [
            r"\.\.[\\/]",
            r"etc[\\/]passwd",
            r"windows[\\/]system",
        ],
        "ssrf": [
            r"169\.254\.169\.254",
            r"metadata\.google\.internal",
            r"localhost:\d+",
        ],
        "command_injection": [
            r"uid=\d+\(.*?\)",
            r"root:x:\d+:\d+",
            r"Permission denied",
        ],
    }

    def __init__(self, ai_router: Optional[AIRouter] = None):
        """
        Initialize AI scanner
        
        Args:
            ai_router: AI router for LLM verification
        """
        self.ai_router = ai_router or AIRouter()

    async def scan_application(
        self,
        base_url: str,
        endpoints: List[str],
        headers: Optional[Dict] = None,
    ) -> List[VulnerabilityFinding]:
        """
        Scan web application for vulnerabilities
        
        Args:
            base_url: Base URL of application
            endpoints: List of endpoints to test
            headers: Custom HTTP headers
        
        Returns:
            List of detected vulnerabilities
        """
        logger.info(f"Starting AI vulnerability scan on {base_url}")
        
        findings = []
        
        for endpoint in endpoints:
            url = f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"
            
            endpoint_findings = await self._scan_endpoint(url, headers)
            findings.extend(endpoint_findings)
        
        verified_findings = await self._verify_findings(findings)
        
        logger.info(
            f"Scan complete: {len(verified_findings)} verified vulnerabilities "
            f"({len(findings)} initial detections)"
        )
        
        return verified_findings

    async def _scan_endpoint(
        self,
        url: str,
        headers: Optional[Dict] = None,
    ) -> List[VulnerabilityFinding]:
        """Scan single endpoint for vulnerabilities"""
        findings = []
        
        sqli_findings = await self._test_sql_injection(url, headers)
        findings.extend(sqli_findings)
        
        xss_findings = await self._test_xss(url, headers)
        findings.extend(xss_findings)
        
        traversal_findings = await self._test_path_traversal(url, headers)
        findings.extend(traversal_findings)
        
        return findings

    async def _test_sql_injection(
        self,
        url: str,
        headers: Optional[Dict] = None,
    ) -> List[VulnerabilityFinding]:
        """Test for SQL injection vulnerabilities"""
        findings = []
        
        payloads = [
            "'",
            "' OR '1'='1",
            "1' AND '1'='1",
            "1 UNION SELECT NULL--",
        ]
        
        parsed = urlparse(url)
        if "?" not in url:
            return findings
        
        async with aiohttp.ClientSession() as session:
            for payload in payloads:
                test_url = url.replace("=", f"={payload}")
                
                try:
                    async with session.get(
                        test_url,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as response:
                        body = await response.text()
                        
                        for pattern in self.VULNERABILITY_PATTERNS["sqli"]:
                            import re
                            if re.search(pattern, body, re.IGNORECASE):
                                finding = VulnerabilityFinding(
                                    title="SQL Injection Detected",
                                    description=(
                                        "The application returned a database error "
                                        "when injecting SQL metacharacters, indicating "
                                        "possible SQL injection vulnerability."
                                    ),
                                    severity="HIGH",
                                    confidence=0.7,
                                    affected_url=test_url,
                                    http_method="GET",
                                    vulnerable_parameter=self._extract_parameter(url),
                                    evidence=pattern,
                                    attack_vector=payload,
                                    remediation=(
                                        "Use parameterized queries or prepared statements. "
                                        "Never concatenate user input directly into SQL."
                                    ),
                                    cwe_id="CWE-89",
                                )
                                findings.append(finding)
                                break
                
                except Exception as e:
                    logger.debug(f"Error testing SQLi on {test_url}: {e}")
        
        return findings

    async def _test_xss(
        self,
        url: str,
        headers: Optional[Dict] = None,
    ) -> List[VulnerabilityFinding]:
        """Test for Cross-Site Scripting vulnerabilities"""
        findings = []
        
        payloads = [
            "<script>alert('XSS')</script>",
            "<img src=x onerror=alert('XSS')>",
            "javascript:alert('XSS')",
        ]
        
        if "?" not in url:
            return findings
        
        async with aiohttp.ClientSession() as session:
            for payload in payloads:
                test_url = url.replace("=", f"={payload}")
                
                try:
                    async with session.get(
                        test_url,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as response:
                        body = await response.text()
                        
                        if payload in body:
                            finding = VulnerabilityFinding(
                                title="Cross-Site Scripting (XSS) Detected",
                                description=(
                                    "User input is reflected in the response without "
                                    "proper sanitization, allowing injection of malicious scripts."
                                ),
                                severity="MEDIUM",
                                confidence=0.8,
                                affected_url=test_url,
                                http_method="GET",
                                vulnerable_parameter=self._extract_parameter(url),
                                evidence=f"Payload reflected: {payload[:50]}",
                                attack_vector=payload,
                                remediation=(
                                    "Encode all user input before rendering in HTML. "
                                    "Use Content Security Policy headers."
                                ),
                                cwe_id="CWE-79",
                            )
                            findings.append(finding)
                            break
                
                except Exception as e:
                    logger.debug(f"Error testing XSS on {test_url}: {e}")
        
        return findings

    async def _test_path_traversal(
        self,
        url: str,
        headers: Optional[Dict] = None,
    ) -> List[VulnerabilityFinding]:
        """Test for path traversal vulnerabilities"""
        findings = []
        
        payloads = [
            "../../../../../etc/passwd",
            "..\\..\\..\\..\\windows\\system32\\drivers\\etc\\hosts",
        ]
        
        if "?" not in url:
            return findings
        
        async with aiohttp.ClientSession() as session:
            for payload in payloads:
                test_url = url.replace("=", f"={payload}")
                
                try:
                    async with session.get(
                        test_url,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as response:
                        body = await response.text()
                        
                        for pattern in self.VULNERABILITY_PATTERNS["path_traversal"]:
                            import re
                            if re.search(pattern, body, re.IGNORECASE):
                                finding = VulnerabilityFinding(
                                    title="Path Traversal Detected",
                                    description=(
                                        "The application allows access to files outside "
                                        "the intended directory through path traversal."
                                    ),
                                    severity="HIGH",
                                    confidence=0.75,
                                    affected_url=test_url,
                                    http_method="GET",
                                    vulnerable_parameter=self._extract_parameter(url),
                                    evidence=pattern,
                                    attack_vector=payload,
                                    remediation=(
                                        "Validate and sanitize file paths. Use whitelist "
                                        "of allowed files. Never trust user input for file operations."
                                    ),
                                    cwe_id="CWE-22",
                                )
                                findings.append(finding)
                                break
                
                except Exception as e:
                    logger.debug(f"Error testing path traversal on {test_url}: {e}")
        
        return findings

    async def _verify_findings(
        self,
        findings: List[VulnerabilityFinding],
    ) -> List[VulnerabilityFinding]:
        """
        Use AI to verify findings and filter false positives
        
        Args:
            findings: Initial vulnerability findings
        
        Returns:
            Verified findings with updated confidence scores
        """
        verified = []
        
        for finding in findings:
            prompt = f"""
            Analyze this potential vulnerability and determine if it's a real issue:
            
            Title: {finding.title}
            URL: {finding.affected_url}
            Method: {finding.http_method}
            Parameter: {finding.vulnerable_parameter}
            Attack Vector: {finding.attack_vector}
            Evidence: {finding.evidence}
            
            Consider:
            1. Is this a genuine vulnerability or false positive?
            2. What's the real-world exploitability?
            3. Are there any mitigating factors?
            
            Respond with JSON:
            {{"verified": true/false, "confidence": 0.0-1.0, "reasoning": "..."}}
            """
            
            try:
                response = await self.ai_router.route_request(
                    prompt=prompt,
                    task_type="reasoning",
                )
                
                import json
                import re
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    analysis = json.loads(json_match.group())
                    
                    if analysis.get("verified", False):
                        finding.verified = True
                        finding.confidence = float(analysis.get("confidence", finding.confidence))
                        verified.append(finding)
                        logger.debug(f"Verified: {finding.title} (confidence: {finding.confidence:.2f})")
                
            except Exception as e:
                logger.warning(f"Error verifying finding: {e}")
                if finding.confidence >= 0.7:
                    verified.append(finding)
        
        return verified

    def _extract_parameter(self, url: str) -> Optional[str]:
        """Extract vulnerable parameter name from URL"""
        parsed = urlparse(url)
        if parsed.query:
            params = parsed.query.split("&")
            if params:
                return params[0].split("=")[0]
        return None
