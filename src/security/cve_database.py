"""
CVE Database - Comprehensive vulnerability database with NVD integration
Stores and searches 200k+ CVE records with CVSS scoring
"""

import asyncio
import gzip
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional
from urllib.parse import urljoin

import aiohttp
from loguru import logger
from sqlalchemy import select, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.session import get_db_session
from src.security.models import CVEModel, SeverityLevel


@dataclass
class CVEEntry:
    """CVE entry data structure"""

    cve_id: str
    published_date: datetime
    last_modified_date: datetime
    description: str
    cvss_score: Optional[float]
    cvss_vector: Optional[str]
    cvss_version: Optional[str]
    severity: str
    cpe_matches: Optional[List[dict]]
    references: Optional[List[dict]]
    exploit_available: bool = False
    metasploit_module: Optional[str] = None
    exploitdb_id: Optional[str] = None


class CVEDatabase:
    """
    CVE vulnerability database manager
    
    Features:
    - Local CVE database (200k+ entries)
    - NVD API integration
    - Fast keyword search
    - CVSS score filtering
    - Exploit availability tracking
    """

    NVD_BASE_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
    NVD_RATE_LIMIT = 5  # requests per 30 seconds (free tier)
    DATA_DIR = Path("data/cve")

    def __init__(self):
        """Initialize CVE database"""
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._request_timestamps: List[float] = []

    async def initialize(self) -> None:
        """Initialize database and download CVE data if needed"""
        logger.info("Initializing CVE database...")
        
        async with get_db_session() as db:
            count = await self.get_cve_count(db)
            logger.info(f"CVE database contains {count:,} entries")
            
            if count < 1000:
                logger.warning("CVE database is empty or incomplete. Run sync to populate.")

    async def get_cve_count(self, db: AsyncSession) -> int:
        """Get total number of CVEs in database"""
        result = await db.execute(select(func.count(CVEModel.id)))
        return result.scalar() or 0

    async def get_cve_by_id(self, cve_id: str, db: AsyncSession) -> Optional[CVEEntry]:
        """
        Retrieve CVE by ID
        
        Args:
            cve_id: CVE identifier (e.g., CVE-2024-1234)
            db: Database session
        
        Returns:
            CVEEntry if found, None otherwise
        """
        result = await db.execute(
            select(CVEModel).where(CVEModel.cve_id == cve_id.upper())
        )
        cve_model = result.scalar_one_or_none()
        
        if not cve_model:
            logger.warning(f"CVE {cve_id} not found in local database")
            cve_model = await self._fetch_from_nvd(cve_id, db)
        
        if cve_model:
            return self._model_to_entry(cve_model)
        return None

    async def search_cves(
        self,
        db: AsyncSession,
        keyword: Optional[str] = None,
        severity: Optional[str] = None,
        min_cvss_score: Optional[float] = None,
        max_cvss_score: Optional[float] = None,
        has_exploit: Optional[bool] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[CVEEntry]:
        """
        Search CVEs with filters
        
        Args:
            db: Database session
            keyword: Search in description
            severity: Filter by severity level
            min_cvss_score: Minimum CVSS score
            max_cvss_score: Maximum CVSS score
            has_exploit: Filter by exploit availability
            limit: Max results to return
            offset: Pagination offset
        
        Returns:
            List of matching CVE entries
        """
        query = select(CVEModel)
        filters = []

        if keyword:
            keyword_lower = f"%{keyword.lower()}%"
            filters.append(
                or_(
                    CVEModel.cve_id.ilike(keyword_lower),
                    CVEModel.description.ilike(keyword_lower),
                )
            )

        if severity:
            filters.append(CVEModel.severity == severity.upper())

        if min_cvss_score is not None:
            filters.append(CVEModel.cvss_score >= min_cvss_score)

        if max_cvss_score is not None:
            filters.append(CVEModel.cvss_score <= max_cvss_score)

        if has_exploit is not None:
            filters.append(CVEModel.exploit_available == (1 if has_exploit else 0))

        if filters:
            query = query.where(and_(*filters))

        query = query.order_by(CVEModel.cvss_score.desc().nullslast())
        query = query.limit(limit).offset(offset)

        result = await db.execute(query)
        cve_models = result.scalars().all()

        return [self._model_to_entry(cve) for cve in cve_models]

    async def _fetch_from_nvd(
        self, cve_id: str, db: AsyncSession
    ) -> Optional[CVEModel]:
        """
        Fetch CVE from NVD API and cache locally
        
        Args:
            cve_id: CVE identifier
            db: Database session
        
        Returns:
            CVEModel if found and stored
        """
        await self._rate_limit()

        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.NVD_BASE_URL}"
                params = {"cveId": cve_id}
                
                async with session.get(url, params=params, timeout=30) as response:
                    if response.status != 200:
                        logger.error(f"NVD API returned {response.status} for {cve_id}")
                        return None
                    
                    data = await response.json()
                    
                    if not data.get("vulnerabilities"):
                        logger.warning(f"CVE {cve_id} not found in NVD")
                        return None
                    
                    cve_item = data["vulnerabilities"][0]["cve"]
                    cve_model = await self._parse_nvd_cve(cve_item, db)
                    
                    if cve_model:
                        logger.info(f"Cached CVE {cve_id} from NVD")
                    
                    return cve_model

        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching {cve_id} from NVD")
        except Exception as e:
            logger.error(f"Error fetching {cve_id} from NVD: {e}")
        
        return None

    async def _parse_nvd_cve(
        self, cve_data: dict, db: AsyncSession
    ) -> Optional[CVEModel]:
        """
        Parse NVD CVE JSON and store in database
        
        Args:
            cve_data: CVE data from NVD API
            db: Database session
        
        Returns:
            Stored CVEModel
        """
        try:
            cve_id = cve_data["id"]
            
            description = ""
            if "descriptions" in cve_data:
                for desc in cve_data["descriptions"]:
                    if desc["lang"] == "en":
                        description = desc["value"]
                        break

            published = datetime.fromisoformat(
                cve_data["published"].replace("Z", "+00:00")
            )
            last_modified = datetime.fromisoformat(
                cve_data["lastModified"].replace("Z", "+00:00")
            )

            cvss_score = None
            cvss_vector = None
            cvss_version = None
            severity = "NONE"

            if "metrics" in cve_data:
                for metric_version in ["cvssMetricV31", "cvssMetricV30", "cvssMetricV2"]:
                    if metric_version in cve_data["metrics"]:
                        metric = cve_data["metrics"][metric_version][0]
                        cvss_data = metric.get("cvssData", {})
                        cvss_score = cvss_data.get("baseScore")
                        cvss_vector = cvss_data.get("vectorString")
                        cvss_version = cvss_data.get("version", "2.0")
                        severity = metric.get("baseSeverity", "NONE").upper()
                        break

            references = []
            if "references" in cve_data:
                references = [
                    {"url": ref.get("url"), "source": ref.get("source")}
                    for ref in cve_data["references"]
                ]

            cpe_matches = []
            if "configurations" in cve_data:
                for config in cve_data["configurations"]:
                    for node in config.get("nodes", []):
                        for match in node.get("cpeMatch", []):
                            if match.get("vulnerable"):
                                cpe_matches.append(
                                    {
                                        "criteria": match.get("criteria"),
                                        "version_start": match.get("versionStartIncluding"),
                                        "version_end": match.get("versionEndIncluding"),
                                    }
                                )

            cve_model = CVEModel(
                cve_id=cve_id,
                published_date=published,
                last_modified_date=last_modified,
                description=description,
                cvss_score=cvss_score,
                cvss_vector=cvss_vector,
                cvss_version=cvss_version,
                severity=severity,
                cpe_matches=cpe_matches,
                references=references,
                exploit_available=0,
            )

            db.add(cve_model)
            await db.commit()
            await db.refresh(cve_model)

            return cve_model

        except Exception as e:
            logger.error(f"Error parsing CVE data: {e}")
            await db.rollback()
            return None

    async def _rate_limit(self) -> None:
        """Enforce NVD API rate limiting (5 requests per 30 seconds)"""
        now = asyncio.get_event_loop().time()
        
        self._request_timestamps = [
            ts for ts in self._request_timestamps if now - ts < 30
        ]
        
        if len(self._request_timestamps) >= self.NVD_RATE_LIMIT:
            oldest = self._request_timestamps[0]
            wait_time = 30 - (now - oldest) + 0.5
            if wait_time > 0:
                logger.debug(f"Rate limiting: waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)
        
        self._request_timestamps.append(now)

    def _model_to_entry(self, model: CVEModel) -> CVEEntry:
        """Convert CVEModel to CVEEntry dataclass"""
        return CVEEntry(
            cve_id=model.cve_id,
            published_date=model.published_date,
            last_modified_date=model.last_modified_date,
            description=model.description,
            cvss_score=model.cvss_score,
            cvss_vector=model.cvss_vector,
            cvss_version=model.cvss_version,
            severity=model.severity,
            cpe_matches=model.cpe_matches,
            references=model.references,
            exploit_available=bool(model.exploit_available),
            metasploit_module=model.metasploit_module,
            exploitdb_id=model.exploitdb_id,
        )

    async def sync_recent_cves(
        self, db: AsyncSession, days: int = 30
    ) -> int:
        """
        Sync CVEs from last N days from NVD
        
        Args:
            db: Database session
            days: Number of days to sync
        
        Returns:
            Number of CVEs synced
        """
        logger.info(f"Syncing CVEs from last {days} days...")
        
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        synced = 0
        start_index = 0
        results_per_page = 2000

        try:
            async with aiohttp.ClientSession() as session:
                while True:
                    await self._rate_limit()
                    
                    url = f"{self.NVD_BASE_URL}"
                    params = {
                        "pubStartDate": start_date.strftime("%Y-%m-%dT%H:%M:%S.000"),
                        "pubEndDate": end_date.strftime("%Y-%m-%dT%H:%M:%S.000"),
                        "startIndex": start_index,
                        "resultsPerPage": results_per_page,
                    }
                    
                    async with session.get(url, params=params, timeout=60) as response:
                        if response.status != 200:
                            logger.error(f"NVD API error: {response.status}")
                            break
                        
                        data = await response.json()
                        
                        vulnerabilities = data.get("vulnerabilities", [])
                        if not vulnerabilities:
                            break
                        
                        for vuln in vulnerabilities:
                            cve_item = vuln["cve"]
                            await self._parse_nvd_cve(cve_item, db)
                            synced += 1
                        
                        total_results = data.get("totalResults", 0)
                        if start_index + results_per_page >= total_results:
                            break
                        
                        start_index += results_per_page
                        logger.info(f"Synced {synced}/{total_results} CVEs...")

        except Exception as e:
            logger.error(f"Error syncing CVEs: {e}")
        
        logger.info(f"Sync complete: {synced} CVEs added/updated")
        return synced
