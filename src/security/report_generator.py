"""
Security Report Generator
Professional vulnerability assessment reports in multiple formats
"""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger

from src.security.ai_scanner import VulnerabilityFinding
from src.security.cvss_calculator import CVSSScore


@dataclass
class SecurityReport:
    """Security assessment report"""
    title: str
    target: str
    scan_date: datetime
    findings: List[VulnerabilityFinding]
    executive_summary: str
    statistics: Dict[str, int]
    recommendations: List[str]


class SecurityReportGenerator:
    """
    Professional security report generator
    
    Features:
    - HTML reports (styled, interactive)
    - Markdown reports (GitHub-friendly)
    - JSON reports (machine-readable)
    - PDF export (coming soon)
    - Executive summaries
    - CVSS scoring
    - Remediation guidance
    """

    def __init__(self):
        """Initialize report generator"""
        self.output_dir = Path("data/security_reports")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_report(
        self,
        target: str,
        findings: List[VulnerabilityFinding],
        scan_date: Optional[datetime] = None,
        title: Optional[str] = None,
    ) -> SecurityReport:
        """
        Generate security report from findings
        
        Args:
            target: Target application/URL
            findings: List of vulnerability findings
            scan_date: When scan was performed
            title: Report title
        
        Returns:
            SecurityReport object
        """
        scan_date = scan_date or datetime.now()
        title = title or f"Security Assessment - {target}"
        
        statistics = self._calculate_statistics(findings)
        executive_summary = self._generate_executive_summary(target, statistics)
        recommendations = self._generate_recommendations(findings)
        
        report = SecurityReport(
            title=title,
            target=target,
            scan_date=scan_date,
            findings=findings,
            executive_summary=executive_summary,
            statistics=statistics,
            recommendations=recommendations,
        )
        
        logger.info(f"Generated security report with {len(findings)} findings")
        return report

    def export_html(self, report: SecurityReport, output_path: str) -> str:
        """
        Export report as styled HTML
        
        Args:
            report: Security report
            output_path: Output file path
        
        Returns:
            Path to saved HTML file
        """
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{report.title}</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .header h1 {{
            margin: 0 0 10px 0;
            font-size: 2.5em;
        }}
        .metadata {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .metadata-card {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .metadata-card h3 {{
            margin: 0 0 10px 0;
            color: #667eea;
            font-size: 0.9em;
            text-transform: uppercase;
        }}
        .metadata-card p {{
            margin: 0;
            font-size: 1.8em;
            font-weight: bold;
        }}
        .section {{
            background: white;
            padding: 30px;
            margin-bottom: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .section h2 {{
            color: #667eea;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
            margin-top: 0;
        }}
        .severity-critical {{
            background-color: #dc3545;
            color: white;
        }}
        .severity-high {{
            background-color: #fd7e14;
            color: white;
        }}
        .severity-medium {{
            background-color: #ffc107;
            color: #333;
        }}
        .severity-low {{
            background-color: #28a745;
            color: white;
        }}
        .severity-badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 4px;
            font-size: 0.85em;
            font-weight: bold;
            text-transform: uppercase;
        }}
        .finding {{
            border-left: 4px solid #667eea;
            padding: 20px;
            margin-bottom: 20px;
            background: #f8f9fa;
            border-radius: 4px;
        }}
        .finding h3 {{
            margin: 0 0 10px 0;
            color: #333;
        }}
        .finding-meta {{
            color: #666;
            font-size: 0.9em;
            margin-bottom: 15px;
        }}
        .code-block {{
            background: #2d2d2d;
            color: #f8f8f2;
            padding: 15px;
            border-radius: 4px;
            overflow-x: auto;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
        }}
        .recommendation {{
            padding: 15px;
            background: #e7f3ff;
            border-left: 4px solid #0066cc;
            margin-bottom: 15px;
            border-radius: 4px;
        }}
        .chart {{
            margin: 20px 0;
        }}
        footer {{
            text-align: center;
            padding: 20px;
            color: #666;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{report.title}</h1>
        <p>Target: {report.target}</p>
        <p>Scan Date: {report.scan_date.strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>

    <div class="metadata">
        <div class="metadata-card">
            <h3>Total Findings</h3>
            <p>{report.statistics['total']}</p>
        </div>
        <div class="metadata-card">
            <h3>Critical</h3>
            <p style="color: #dc3545;">{report.statistics['critical']}</p>
        </div>
        <div class="metadata-card">
            <h3>High</h3>
            <p style="color: #fd7e14;">{report.statistics['high']}</p>
        </div>
        <div class="metadata-card">
            <h3>Medium</h3>
            <p style="color: #ffc107;">{report.statistics['medium']}</p>
        </div>
        <div class="metadata-card">
            <h3>Low</h3>
            <p style="color: #28a745;">{report.statistics['low']}</p>
        </div>
    </div>

    <div class="section">
        <h2>Executive Summary</h2>
        <p>{report.executive_summary}</p>
    </div>

    <div class="section">
        <h2>Findings ({len(report.findings)})</h2>
        {self._generate_findings_html(report.findings)}
    </div>

    <div class="section">
        <h2>Recommendations</h2>
        {self._generate_recommendations_html(report.recommendations)}
    </div>

    <footer>
        <p>Generated by Ironclaw Security Suite</p>
        <p>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </footer>
</body>
</html>"""

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        
        logger.info(f"Exported HTML report to {output_path}")
        return output_path

    def export_markdown(self, report: SecurityReport, output_path: str) -> str:
        """
        Export report as Markdown
        
        Args:
            report: Security report
            output_path: Output file path
        
        Returns:
            Path to saved Markdown file
        """
        md = f"""# {report.title}

## Target Information
- **Target**: {report.target}
- **Scan Date**: {report.scan_date.strftime('%Y-%m-%d %H:%M:%S')}
- **Total Findings**: {report.statistics['total']}

## Statistics

| Severity | Count |
|----------|-------|
| Critical | {report.statistics['critical']} |
| High     | {report.statistics['high']} |
| Medium   | {report.statistics['medium']} |
| Low      | {report.statistics['low']} |

## Executive Summary

{report.executive_summary}

## Detailed Findings

{self._generate_findings_markdown(report.findings)}

## Recommendations

{self._generate_recommendations_markdown(report.recommendations)}

---

*Generated by Ironclaw Security Suite on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(md)
        
        logger.info(f"Exported Markdown report to {output_path}")
        return output_path

    def export_json(self, report: SecurityReport, output_path: str) -> str:
        """
        Export report as JSON
        
        Args:
            report: Security report
            output_path: Output file path
        
        Returns:
            Path to saved JSON file
        """
        data = {
            "title": report.title,
            "target": report.target,
            "scan_date": report.scan_date.isoformat(),
            "statistics": report.statistics,
            "executive_summary": report.executive_summary,
            "findings": [
                {
                    "title": f.title,
                    "description": f.description,
                    "severity": f.severity,
                    "confidence": f.confidence,
                    "affected_url": f.affected_url,
                    "http_method": f.http_method,
                    "vulnerable_parameter": f.vulnerable_parameter,
                    "evidence": f.evidence,
                    "attack_vector": f.attack_vector,
                    "remediation": f.remediation,
                    "cwe_id": f.cwe_id,
                    "verified": f.verified,
                }
                for f in report.findings
            ],
            "recommendations": report.recommendations,
        }
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Exported JSON report to {output_path}")
        return output_path

    def _calculate_statistics(self, findings: List[VulnerabilityFinding]) -> Dict[str, int]:
        """Calculate vulnerability statistics"""
        stats = {
            "total": len(findings),
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "verified": 0,
        }
        
        for finding in findings:
            severity = finding.severity.upper()
            if severity == "CRITICAL":
                stats["critical"] += 1
            elif severity == "HIGH":
                stats["high"] += 1
            elif severity == "MEDIUM":
                stats["medium"] += 1
            elif severity == "LOW":
                stats["low"] += 1
            
            if finding.verified:
                stats["verified"] += 1
        
        return stats

    def _generate_executive_summary(self, target: str, stats: Dict[str, int]) -> str:
        """Generate executive summary"""
        summary = f"""
A comprehensive security assessment was conducted on {target}. 
The assessment identified {stats['total']} potential security vulnerabilities, 
including {stats['critical']} critical, {stats['high']} high, 
{stats['medium']} medium, and {stats['low']} low severity issues.

{stats['verified']} findings have been verified through AI-powered analysis. 
Immediate attention is recommended for all critical and high-severity vulnerabilities.
        """.strip()
        
        return summary

    def _generate_recommendations(self, findings: List[VulnerabilityFinding]) -> List[str]:
        """Generate remediation recommendations"""
        recommendations = [
            "Implement a Web Application Firewall (WAF) to filter malicious requests",
            "Enable HTTPS/TLS encryption for all communications",
            "Implement proper input validation and output encoding",
            "Apply principle of least privilege for system accounts",
            "Keep all software and dependencies up to date",
            "Conduct regular security assessments and penetration tests",
            "Implement security headers (CSP, HSTS, X-Frame-Options)",
            "Enable comprehensive logging and monitoring",
        ]
        
        vuln_types = set(f.cwe_id for f in findings if f.cwe_id)
        if "CWE-89" in vuln_types:
            recommendations.insert(0, "Use parameterized queries to prevent SQL injection")
        if "CWE-79" in vuln_types:
            recommendations.insert(0, "Implement context-aware output encoding to prevent XSS")
        if "CWE-22" in vuln_types:
            recommendations.insert(0, "Validate and sanitize file paths to prevent traversal attacks")
        
        return recommendations[:10]

    def _generate_findings_html(self, findings: List[VulnerabilityFinding]) -> str:
        """Generate HTML for findings section"""
        html_parts = []
        
        for i, finding in enumerate(findings, 1):
            severity_class = f"severity-{finding.severity.lower()}"
            
            html_parts.append(f"""
        <div class="finding">
            <h3>{i}. {finding.title} <span class="severity-badge {severity_class}">{finding.severity}</span></h3>
            <div class="finding-meta">
                <strong>URL:</strong> {finding.affected_url}<br>
                <strong>Method:</strong> {finding.http_method}<br>
                <strong>Parameter:</strong> {finding.vulnerable_parameter or 'N/A'}<br>
                <strong>CWE:</strong> {finding.cwe_id or 'N/A'}<br>
                <strong>Confidence:</strong> {finding.confidence:.0%}<br>
                <strong>Verified:</strong> {'✅ Yes' if finding.verified else '❌ No'}
            </div>
            <p><strong>Description:</strong> {finding.description}</p>
            <p><strong>Evidence:</strong></p>
            <div class="code-block">{finding.evidence}</div>
            <p><strong>Attack Vector:</strong></p>
            <div class="code-block">{finding.attack_vector}</div>
            <p><strong>Remediation:</strong> {finding.remediation}</p>
        </div>
            """)
        
        return "\n".join(html_parts)

    def _generate_recommendations_html(self, recommendations: List[str]) -> str:
        """Generate HTML for recommendations"""
        html_parts = []
        
        for i, rec in enumerate(recommendations, 1):
            html_parts.append(f"""
        <div class="recommendation">
            <strong>{i}.</strong> {rec}
        </div>
            """)
        
        return "\n".join(html_parts)

    def _generate_findings_markdown(self, findings: List[VulnerabilityFinding]) -> str:
        """Generate Markdown for findings"""
        md_parts = []
        
        for i, finding in enumerate(findings, 1):
            md_parts.append(f"""
### {i}. {finding.title} [{finding.severity}]

**URL**: `{finding.affected_url}`  
**Method**: `{finding.http_method}`  
**Parameter**: `{finding.vulnerable_parameter or 'N/A'}`  
**CWE**: `{finding.cwe_id or 'N/A'}`  
**Confidence**: {finding.confidence:.0%}  
**Verified**: {'✅ Yes' if finding.verified else '❌ No'}

**Description**: {finding.description}

**Evidence**:
```
{finding.evidence}
```

**Attack Vector**:
```
{finding.attack_vector}
```

**Remediation**: {finding.remediation}
            """)
        
        return "\n".join(md_parts)

    def _generate_recommendations_markdown(self, recommendations: List[str]) -> str:
        """Generate Markdown for recommendations"""
        return "\n".join(f"{i}. {rec}" for i, rec in enumerate(recommendations, 1))
