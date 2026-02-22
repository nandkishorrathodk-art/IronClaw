"""
Nuclei Template-Based Vulnerability Scanner Integration
Fast, template-driven security scanning
"""

import asyncio
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from loguru import logger


@dataclass
class NucleiResult:
    """Nuclei scan result"""
    template_id: str
    template_name: str
    severity: str
    matched_at: str
    extracted_results: Optional[List[str]] = None
    curl_command: Optional[str] = None
    matcher_name: Optional[str] = None
    description: Optional[str] = None
    reference: Optional[List[str]] = None
    cve_id: Optional[str] = None
    cvss_score: Optional[float] = None


class NucleiScanner:
    """
    Nuclei vulnerability scanner integration
    
    Features:
    - Template-based scanning (10,000+ templates)
    - Automatic template updates
    - Fast parallel scanning
    - JSON output parsing
    
    Requires:
    - nuclei binary installed (https://github.com/projectdiscovery/nuclei)
    """

    def __init__(
        self,
        nuclei_binary: str = "nuclei",
        templates_dir: Optional[str] = None,
        rate_limit: int = 150,
        timeout: int = 5,
    ):
        """
        Initialize Nuclei scanner
        
        Args:
            nuclei_binary: Path to nuclei binary
            templates_dir: Custom templates directory
            rate_limit: Max requests per second
            timeout: Request timeout in seconds
        """
        self.nuclei_binary = nuclei_binary
        self.templates_dir = templates_dir
        self.rate_limit = rate_limit
        self.timeout = timeout

    async def check_installed(self) -> bool:
        """
        Check if Nuclei is installed
        
        Returns:
            True if nuclei binary is available
        """
        nuclei_path = shutil.which(self.nuclei_binary)
        if nuclei_path:
            logger.info(f"Nuclei found at: {nuclei_path}")
            return True
        else:
            logger.warning(
                "Nuclei not found. Install from: "
                "https://github.com/projectdiscovery/nuclei"
            )
            return False

    async def update_templates(self) -> bool:
        """
        Update Nuclei templates to latest version
        
        Returns:
            True if update succeeded
        """
        try:
            cmd = [self.nuclei_binary, "-update-templates"]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                logger.info("Nuclei templates updated successfully")
                return True
            else:
                logger.error(f"Template update failed: {stderr.decode()}")
                return False
        
        except Exception as e:
            logger.error(f"Error updating Nuclei templates: {e}")
            return False

    async def scan_target(
        self,
        target: str,
        severity: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        templates: Optional[List[str]] = None,
        exclude_tags: Optional[List[str]] = None,
    ) -> List[NucleiResult]:
        """
        Scan target with Nuclei
        
        Args:
            target: Target URL or IP
            severity: Filter by severity (critical, high, medium, low, info)
            tags: Filter by tags (e.g., cve, rce, sqli, xss)
            templates: Specific templates to run
            exclude_tags: Tags to exclude
        
        Returns:
            List of vulnerability findings
        """
        if not await self.check_installed():
            logger.error("Nuclei not installed, cannot scan")
            return []

        cmd = [
            self.nuclei_binary,
            "-target", target,
            "-json",
            "-silent",
            "-rate-limit", str(self.rate_limit),
            "-timeout", str(self.timeout),
        ]

        if severity:
            cmd.extend(["-severity", ",".join(severity)])

        if tags:
            cmd.extend(["-tags", ",".join(tags)])

        if templates:
            for template in templates:
                cmd.extend(["-t", template])

        if exclude_tags:
            cmd.extend(["-exclude-tags", ",".join(exclude_tags)])

        if self.templates_dir:
            cmd.extend(["-t", self.templates_dir])

        logger.info(f"Starting Nuclei scan on {target}")
        logger.debug(f"Command: {' '.join(cmd)}")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0 and stderr:
                logger.warning(f"Nuclei stderr: {stderr.decode()}")

            results = []
            for line in stdout.decode().strip().split("\n"):
                if not line:
                    continue
                
                try:
                    data = json.loads(line)
                    result = self._parse_result(data)
                    results.append(result)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse Nuclei output: {line}")
                    continue

            logger.info(f"Nuclei scan complete: {len(results)} findings")
            return results

        except Exception as e:
            logger.error(f"Error running Nuclei scan: {e}")
            return []

    def _parse_result(self, data: dict) -> NucleiResult:
        """Parse Nuclei JSON output into NucleiResult"""
        template_id = data.get("template-id", "unknown")
        info = data.get("info", {})
        
        result = NucleiResult(
            template_id=template_id,
            template_name=info.get("name", template_id),
            severity=info.get("severity", "info").upper(),
            matched_at=data.get("matched-at", ""),
            extracted_results=data.get("extracted-results"),
            curl_command=data.get("curl-command"),
            matcher_name=data.get("matcher-name"),
            description=info.get("description"),
            reference=info.get("reference"),
        )

        tags = info.get("tags", [])
        if isinstance(tags, str):
            tags = tags.split(",")
        
        for tag in tags:
            tag = tag.strip().upper()
            if tag.startswith("CVE-"):
                result.cve_id = tag
                break

        classification = info.get("classification", {})
        if isinstance(classification, dict):
            cvss_score = classification.get("cvss-score")
            if cvss_score:
                result.cvss_score = float(cvss_score)

        return result

    async def scan_multiple_targets(
        self,
        targets: List[str],
        **kwargs,
    ) -> dict[str, List[NucleiResult]]:
        """
        Scan multiple targets in parallel
        
        Args:
            targets: List of target URLs/IPs
            **kwargs: Arguments passed to scan_target
        
        Returns:
            Dictionary mapping targets to their results
        """
        tasks = [self.scan_target(target, **kwargs) for target in targets]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)
        
        results_dict = {}
        for target, results in zip(targets, results_list):
            if isinstance(results, Exception):
                logger.error(f"Error scanning {target}: {results}")
                results_dict[target] = []
            else:
                results_dict[target] = results
        
        total_findings = sum(len(r) for r in results_dict.values())
        logger.info(f"Scanned {len(targets)} targets, {total_findings} total findings")
        
        return results_dict

    async def list_templates(self) -> List[str]:
        """
        List all available Nuclei templates
        
        Returns:
            List of template IDs
        """
        try:
            cmd = [self.nuclei_binary, "-tl", "-silent"]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await process.communicate()
            
            templates = []
            for line in stdout.decode().strip().split("\n"):
                if line:
                    templates.append(line.strip())
            
            logger.info(f"Found {len(templates)} Nuclei templates")
            return templates
        
        except Exception as e:
            logger.error(f"Error listing templates: {e}")
            return []
