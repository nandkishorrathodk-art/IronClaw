"""
Security API Routes
Endpoints for vulnerability scanning, CVE lookup, and security reports
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, Field

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.session import get_db_session
from src.security.orchestrator import SecurityOrchestrator, ScanProfile
from src.security.poc_generator import PoCLanguage


router = APIRouter(prefix="/security", tags=["security"])
orchestrator = SecurityOrchestrator()


class ScanRequest(BaseModel):
    """Request to start security scan"""
    target: str = Field(..., description="Target URL to scan")
    scan_profile: ScanProfile = Field(ScanProfile.STANDARD, description="Scan intensity")
    user_id: Optional[int] = Field(None, description="User initiating scan")


class ScanResponse(BaseModel):
    """Response with scan ID"""
    scan_id: str
    message: str
    target: str
    status: str = "queued"


class CVESearchRequest(BaseModel):
    """CVE search parameters"""
    keyword: Optional[str] = Field(None, description="Search keyword")
    severity: Optional[str] = Field(None, description="Filter by severity")
    min_cvss_score: Optional[float] = Field(None, ge=0.0, le=10.0)
    max_cvss_score: Optional[float] = Field(None, ge=0.0, le=10.0)
    has_exploit: Optional[bool] = Field(None, description="Filter by exploit availability")
    limit: int = Field(100, ge=1, le=500)
    offset: int = Field(0, ge=0)


class ReportRequest(BaseModel):
    """Request to generate report"""
    scan_id: str
    output_format: str = Field("html", pattern="^(html|markdown|json)$")
    output_dir: Optional[str] = None


class PoCRequest(BaseModel):
    """Request to generate PoC"""
    finding_id: str
    language: PoCLanguage = PoCLanguage.PYTHON
    output_dir: Optional[str] = None


@router.on_event("startup")
async def startup_security():
    """Initialize security suite on startup"""
    try:
        await orchestrator.initialize()
        logger.info("Security suite initialized")
    except Exception as e:
        logger.error(f"Failed to initialize security suite: {e}")


@router.post("/scan", response_model=ScanResponse)
async def start_security_scan(
    request: ScanRequest,
    background_tasks: BackgroundTasks,
):
    """
    Start comprehensive security scan
    
    Runs vulnerability scanning with selected profile:
    - **quick**: Fast Nuclei scan (critical/high only)
    - **standard**: Nuclei + AI scanner
    - **full**: Nuclei + AI + custom checks
    - **deep**: All scanners including Burp Suite
    
    Returns scan ID for tracking progress.
    """
    try:
        logger.info(f"Starting scan on {request.target} with profile {request.scan_profile}")
        
        scan_id = await orchestrator.comprehensive_scan(
            target=request.target,
            scan_profile=request.scan_profile,
            user_id=request.user_id,
        )
        
        return ScanResponse(
            scan_id=scan_id,
            message="Scan started successfully",
            target=request.target,
            status="running",
        )
    
    except Exception as e:
        logger.error(f"Error starting scan: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scan/{scan_id}")
async def get_scan_status(scan_id: str):
    """
    Get scan status and results
    
    Returns current status, progress, and findings for the specified scan.
    """
    try:
        results = await orchestrator.get_scan_results(scan_id)
        return results
    
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error retrieving scan {scan_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cve/{cve_id}")
async def get_cve_details(cve_id: str):
    """
    Get CVE vulnerability details
    
    Retrieves information about a specific CVE including:
    - Description
    - CVSS score and severity
    - Affected products (CPE matches)
    - References and exploit availability
    """
    try:
        async with get_db_session() as db:
            cve = await orchestrator.cve_db.get_cve_by_id(cve_id, db)
        
        if not cve:
            raise HTTPException(status_code=404, detail=f"CVE {cve_id} not found")
        
        return {
            "cve_id": cve.cve_id,
            "published_date": cve.published_date.isoformat(),
            "last_modified": cve.last_modified_date.isoformat(),
            "description": cve.description,
            "cvss_score": cve.cvss_score,
            "cvss_vector": cve.cvss_vector,
            "cvss_version": cve.cvss_version,
            "severity": cve.severity,
            "cpe_matches": cve.cpe_matches,
            "references": cve.references,
            "exploit_available": cve.exploit_available,
            "metasploit_module": cve.metasploit_module,
            "exploitdb_id": cve.exploitdb_id,
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving CVE {cve_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cve/search")
async def search_cves(request: CVESearchRequest):
    """
    Search CVE database
    
    Search for vulnerabilities with filters:
    - Keyword search in descriptions
    - Severity filtering (CRITICAL, HIGH, MEDIUM, LOW)
    - CVSS score range
    - Exploit availability
    
    Returns paginated results.
    """
    try:
        async with get_db_session() as db:
            cves = await orchestrator.cve_db.search_cves(
                db=db,
                keyword=request.keyword,
                severity=request.severity,
                min_cvss_score=request.min_cvss_score,
                max_cvss_score=request.max_cvss_score,
                has_exploit=request.has_exploit,
                limit=request.limit,
                offset=request.offset,
            )
        
        return {
            "count": len(cves),
            "cves": [
                {
                    "cve_id": cve.cve_id,
                    "description": cve.description[:200] + "..." if len(cve.description) > 200 else cve.description,
                    "cvss_score": cve.cvss_score,
                    "severity": cve.severity,
                    "published_date": cve.published_date.isoformat(),
                    "exploit_available": cve.exploit_available,
                }
                for cve in cves
            ],
        }
    
    except Exception as e:
        logger.error(f"Error searching CVEs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cve/sync")
async def sync_cve_database(days: int = Query(30, ge=1, le=365)):
    """
    Sync CVE database from NVD
    
    Downloads and updates CVE records from the last N days.
    This is a long-running operation (may take several minutes).
    
    Args:
        days: Number of days to sync (default: 30)
    """
    try:
        async with get_db_session() as db:
            synced = await orchestrator.cve_db.sync_recent_cves(db, days)
        
        return {
            "message": f"Synced {synced} CVEs from last {days} days",
            "synced_count": synced,
        }
    
    except Exception as e:
        logger.error(f"Error syncing CVE database: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/report", response_model=dict)
async def generate_report(request: ReportRequest):
    """
    Generate security report
    
    Creates professional security assessment report in requested format:
    - **html**: Styled HTML report with charts
    - **markdown**: GitHub-friendly Markdown
    - **json**: Machine-readable JSON
    
    Returns path to generated report file.
    """
    try:
        report_path = await orchestrator.generate_scan_report(
            scan_id=request.scan_id,
            output_format=request.output_format,
            output_dir=request.output_dir,
        )
        
        return {
            "message": "Report generated successfully",
            "scan_id": request.scan_id,
            "format": request.output_format,
            "path": report_path,
        }
    
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error generating report: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/poc", response_model=dict)
async def generate_poc(request: PoCRequest):
    """
    Generate Proof-of-Concept exploit
    
    Creates safe PoC script for verified vulnerability in requested language:
    - **python**: Python script with requests library
    - **bash**: Bash script with curl
    - **javascript**: JavaScript/Node.js script
    - **curl**: Simple curl command
    
    ⚠️ For authorized security testing only!
    """
    try:
        poc_path = await orchestrator.generate_poc_for_finding(
            finding_id=request.finding_id,
            language=request.language,
            output_dir=request.output_dir,
        )
        
        return {
            "message": "PoC generated successfully",
            "finding_id": request.finding_id,
            "language": request.language,
            "path": poc_path,
            "warning": "⚠️ For authorized security testing only!",
        }
    
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error generating PoC: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def security_health_check():
    """
    Check security suite health
    
    Verifies that all security components are operational:
    - CVE database
    - Nuclei scanner
    - Burp Suite (if configured)
    """
    try:
        async with get_db_session() as db:
            cve_count = await orchestrator.cve_db.get_cve_count(db)
        
        nuclei_available = await orchestrator.nuclei.check_installed()
        
        burp_available = False
        if orchestrator.burp_url:
            try:
                from src.security.burp_client import BurpSuiteClient
                async with BurpSuiteClient(orchestrator.burp_url, orchestrator.burp_api_key) as burp:
                    burp_available = await burp.health_check()
            except:
                pass
        
        return {
            "status": "healthy",
            "cve_database": {
                "available": True,
                "record_count": cve_count,
            },
            "nuclei": {
                "available": nuclei_available,
            },
            "burp_suite": {
                "available": burp_available,
                "configured": bool(orchestrator.burp_url),
            },
        }
    
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
        }
