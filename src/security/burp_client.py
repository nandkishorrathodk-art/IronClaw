"""
Burp Suite Professional REST API Client
Automate vulnerability scanning with Burp Suite
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from urllib.parse import urljoin

import aiohttp
from loguru import logger


class ScanType(str, Enum):
    """Burp Suite scan types"""
    CRAWL = "Crawl"
    CRAWL_AND_AUDIT = "CrawlAndAudit"
    AUDIT_ONLY = "AuditOnly"


class ScanStatus(str, Enum):
    """Scan status values"""
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class BurpScan:
    """Burp Suite scan information"""
    scan_id: str
    scan_type: str
    status: str
    target_url: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    issue_count: int = 0
    scan_metrics: Optional[Dict] = None


@dataclass
class BurpIssue:
    """Burp Suite vulnerability issue"""
    issue_type: str
    name: str
    severity: str
    confidence: str
    path: str
    evidence: Optional[str] = None
    remediation: Optional[str] = None


class BurpSuiteClient:
    """
    Burp Suite Professional REST API Client
    
    Features:
    - Start/stop/pause scans
    - Configure scan settings
    - Retrieve scan results
    - Export reports
    
    Requires:
    - Burp Suite Professional 2023.1+ with REST API enabled
    - API key configured
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:1337",
        api_key: Optional[str] = None,
        timeout: int = 300,
    ):
        """
        Initialize Burp Suite client
        
        Args:
            base_url: Burp Suite REST API URL
            api_key: API key for authentication
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        """Async context manager entry"""
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.timeout)
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self._session:
            await self._session.close()

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session"""
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )
        return self._session

    async def _request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[Dict] = None,
        params: Optional[Dict] = None,
    ) -> Dict:
        """
        Make HTTP request to Burp Suite API
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            json_data: JSON body data
            params: Query parameters
        
        Returns:
            Response JSON data
        
        Raises:
            aiohttp.ClientError: On network/API errors
        """
        url = urljoin(self.base_url, endpoint)
        headers = {}
        
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        session = await self._get_session()
        
        try:
            async with session.request(
                method=method,
                url=url,
                json=json_data,
                params=params,
                headers=headers,
            ) as response:
                response.raise_for_status()
                
                if response.status == 204:
                    return {}
                
                return await response.json()
        
        except aiohttp.ClientError as e:
            logger.error(f"Burp API request failed: {method} {url} - {e}")
            raise

    async def health_check(self) -> bool:
        """
        Check if Burp Suite API is available
        
        Returns:
            True if API is reachable, False otherwise
        """
        try:
            await self._request("GET", "/v0.1/")
            logger.info("Burp Suite API is available")
            return True
        except Exception as e:
            logger.error(f"Burp Suite API not available: {e}")
            return False

    async def start_scan(
        self,
        target_url: str,
        scan_type: ScanType = ScanType.CRAWL_AND_AUDIT,
        scan_configurations: Optional[Dict] = None,
    ) -> str:
        """
        Start a new scan
        
        Args:
            target_url: Target URL to scan
            scan_type: Type of scan to run
            scan_configurations: Optional scan configuration overrides
        
        Returns:
            Scan ID
        """
        payload = {
            "urls": [target_url],
            "scan_type": scan_type.value,
        }
        
        if scan_configurations:
            payload["scan_configurations"] = scan_configurations
        
        result = await self._request("POST", "/v0.1/scan", json_data=payload)
        scan_id = result.get("task_id")
        
        logger.info(f"Started Burp scan {scan_id} for {target_url}")
        return scan_id

    async def get_scan_status(self, scan_id: str) -> BurpScan:
        """
        Get scan status and progress
        
        Args:
            scan_id: Scan identifier
        
        Returns:
            BurpScan with current status
        """
        result = await self._request("GET", f"/v0.1/scan/{scan_id}")
        
        scan_status = result.get("scan_status", "unknown")
        scan_metrics = result.get("scan_metrics", {})
        
        issue_count = scan_metrics.get("issue_events", 0)
        
        return BurpScan(
            scan_id=scan_id,
            scan_type=result.get("scan_type", "unknown"),
            status=scan_status,
            target_url=result.get("urls", [""])[0],
            issue_count=issue_count,
            scan_metrics=scan_metrics,
        )

    async def wait_for_scan(
        self,
        scan_id: str,
        poll_interval: int = 10,
        max_wait: int = 3600,
    ) -> BurpScan:
        """
        Wait for scan to complete
        
        Args:
            scan_id: Scan identifier
            poll_interval: Seconds between status checks
            max_wait: Maximum seconds to wait
        
        Returns:
            Final BurpScan status
        
        Raises:
            TimeoutError: If scan doesn't complete in time
        """
        start_time = asyncio.get_event_loop().time()
        
        while True:
            scan = await self.get_scan_status(scan_id)
            
            if scan.status in [ScanStatus.SUCCEEDED.value, ScanStatus.FAILED.value]:
                logger.info(f"Scan {scan_id} completed with status: {scan.status}")
                return scan
            
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > max_wait:
                raise TimeoutError(f"Scan {scan_id} did not complete in {max_wait}s")
            
            logger.debug(f"Scan {scan_id} status: {scan.status}, waiting...")
            await asyncio.sleep(poll_interval)

    async def get_scan_issues(self, scan_id: str) -> List[BurpIssue]:
        """
        Get all issues found in scan
        
        Args:
            scan_id: Scan identifier
        
        Returns:
            List of vulnerability issues
        """
        result = await self._request("GET", f"/v0.1/scan/{scan_id}/issues")
        
        issues = []
        for issue_data in result.get("issue_events", []):
            issue = BurpIssue(
                issue_type=issue_data.get("type_index", "unknown"),
                name=issue_data.get("name", "Unknown"),
                severity=issue_data.get("severity", "info"),
                confidence=issue_data.get("confidence", "tentative"),
                path=issue_data.get("path", ""),
                evidence=issue_data.get("evidence"),
                remediation=issue_data.get("remediation_detail"),
            )
            issues.append(issue)
        
        logger.info(f"Retrieved {len(issues)} issues from scan {scan_id}")
        return issues

    async def stop_scan(self, scan_id: str) -> None:
        """
        Stop a running scan
        
        Args:
            scan_id: Scan identifier
        """
        await self._request("DELETE", f"/v0.1/scan/{scan_id}")
        logger.info(f"Stopped scan {scan_id}")

    async def export_report(
        self,
        scan_id: str,
        output_path: str,
        report_format: str = "html",
    ) -> str:
        """
        Export scan report
        
        Args:
            scan_id: Scan identifier
            output_path: Where to save report
            report_format: Report format (html, xml, json)
        
        Returns:
            Path to saved report
        """
        
        params = {"reportType": report_format}
        result = await self._request(
            "GET",
            f"/v0.1/scan/{scan_id}/report",
            params=params
        )
        
        with open(output_path, "w", encoding="utf-8") as f:
            if report_format == "json":
                import json
                json.dump(result, f, indent=2)
            else:
                f.write(str(result))
        
        logger.info(f"Exported report to {output_path}")
        return output_path

    async def close(self) -> None:
        """Close HTTP session"""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.debug("Burp client session closed")
