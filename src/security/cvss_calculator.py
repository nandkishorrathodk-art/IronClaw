"""
CVSS 3.1 Calculator - Common Vulnerability Scoring System
Calculates severity scores for vulnerabilities
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from loguru import logger


class AttackVector(str, Enum):
    """Attack Vector (AV)"""
    NETWORK = "N"  # 0.85
    ADJACENT = "A"  # 0.62
    LOCAL = "L"  # 0.55
    PHYSICAL = "P"  # 0.20


class AttackComplexity(str, Enum):
    """Attack Complexity (AC)"""
    LOW = "L"  # 0.77
    HIGH = "H"  # 0.44


class PrivilegesRequired(str, Enum):
    """Privileges Required (PR)"""
    NONE = "N"  # 0.85
    LOW = "L"  # 0.62 (unchanged) or 0.68 (changed)
    HIGH = "H"  # 0.27 (unchanged) or 0.50 (changed)


class UserInteraction(str, Enum):
    """User Interaction (UI)"""
    NONE = "N"  # 0.85
    REQUIRED = "R"  # 0.62


class Scope(str, Enum):
    """Scope (S)"""
    UNCHANGED = "U"
    CHANGED = "C"


class ImpactMetric(str, Enum):
    """Confidentiality/Integrity/Availability Impact"""
    NONE = "N"  # 0.00
    LOW = "L"  # 0.22
    HIGH = "H"  # 0.56


@dataclass
class CVSSScore:
    """CVSS 3.1 score result"""
    base_score: float
    impact_score: float
    exploitability_score: float
    severity: str
    vector_string: str


class CVSSCalculator:
    """
    CVSS 3.1 Calculator
    
    Implements the official CVSS v3.1 specification:
    https://www.first.org/cvss/v3.1/specification-document
    
    Features:
    - Base score calculation (0.0-10.0)
    - Impact and exploitability sub-scores
    - Severity rating (NONE, LOW, MEDIUM, HIGH, CRITICAL)
    - Vector string generation
    """

    SEVERITY_THRESHOLDS = {
        "NONE": 0.0,
        "LOW": 0.1,
        "MEDIUM": 4.0,
        "HIGH": 7.0,
        "CRITICAL": 9.0,
    }

    def __init__(self):
        """Initialize CVSS calculator"""
        self._metric_values = {
            # Attack Vector
            AttackVector.NETWORK: 0.85,
            AttackVector.ADJACENT: 0.62,
            AttackVector.LOCAL: 0.55,
            AttackVector.PHYSICAL: 0.20,
            # Attack Complexity
            AttackComplexity.LOW: 0.77,
            AttackComplexity.HIGH: 0.44,
            # Privileges Required (Unchanged)
            (PrivilegesRequired.NONE, Scope.UNCHANGED): 0.85,
            (PrivilegesRequired.LOW, Scope.UNCHANGED): 0.62,
            (PrivilegesRequired.HIGH, Scope.UNCHANGED): 0.27,
            # Privileges Required (Changed)
            (PrivilegesRequired.NONE, Scope.CHANGED): 0.85,
            (PrivilegesRequired.LOW, Scope.CHANGED): 0.68,
            (PrivilegesRequired.HIGH, Scope.CHANGED): 0.50,
            # User Interaction
            UserInteraction.NONE: 0.85,
            UserInteraction.REQUIRED: 0.62,
            # Impact
            ImpactMetric.NONE: 0.00,
            ImpactMetric.LOW: 0.22,
            ImpactMetric.HIGH: 0.56,
        }

    def calculate(
        self,
        attack_vector: AttackVector,
        attack_complexity: AttackComplexity,
        privileges_required: PrivilegesRequired,
        user_interaction: UserInteraction,
        scope: Scope,
        confidentiality_impact: ImpactMetric,
        integrity_impact: ImpactMetric,
        availability_impact: ImpactMetric,
    ) -> CVSSScore:
        """
        Calculate CVSS 3.1 base score
        
        Args:
            attack_vector: Network, Adjacent, Local, or Physical
            attack_complexity: Low or High
            privileges_required: None, Low, or High
            user_interaction: None or Required
            scope: Unchanged or Changed
            confidentiality_impact: None, Low, or High
            integrity_impact: None, Low, or High
            availability_impact: None, Low, or High
        
        Returns:
            CVSSScore with base score, impact, exploitability, severity, and vector
        """
        
        impact_score = self._calculate_impact(
            scope,
            confidentiality_impact,
            integrity_impact,
            availability_impact,
        )
        
        exploitability_score = self._calculate_exploitability(
            attack_vector,
            attack_complexity,
            privileges_required,
            user_interaction,
            scope,
        )
        
        if impact_score <= 0:
            base_score = 0.0
        else:
            if scope == Scope.UNCHANGED:
                base_score = min(
                    impact_score + exploitability_score,
                    10.0
                )
            else:
                base_score = min(
                    1.08 * (impact_score + exploitability_score),
                    10.0
                )
        
        base_score = self._round_up(base_score)
        
        severity = self._get_severity(base_score)
        
        vector_string = self._build_vector_string(
            attack_vector,
            attack_complexity,
            privileges_required,
            user_interaction,
            scope,
            confidentiality_impact,
            integrity_impact,
            availability_impact,
        )
        
        logger.debug(
            f"CVSS Calculated: Base={base_score}, "
            f"Impact={impact_score:.2f}, "
            f"Exploitability={exploitability_score:.2f}, "
            f"Severity={severity}"
        )
        
        return CVSSScore(
            base_score=base_score,
            impact_score=impact_score,
            exploitability_score=exploitability_score,
            severity=severity,
            vector_string=vector_string,
        )

    def _calculate_impact(
        self,
        scope: Scope,
        conf_impact: ImpactMetric,
        integ_impact: ImpactMetric,
        avail_impact: ImpactMetric,
    ) -> float:
        """Calculate impact sub-score"""
        
        isc_base = 1 - (
            (1 - self._metric_values[conf_impact]) *
            (1 - self._metric_values[integ_impact]) *
            (1 - self._metric_values[avail_impact])
        )
        
        if scope == Scope.UNCHANGED:
            impact = 6.42 * isc_base
        else:
            impact = 7.52 * (isc_base - 0.029) - 3.25 * pow(isc_base - 0.02, 15)
        
        return max(0.0, impact)

    def _calculate_exploitability(
        self,
        av: AttackVector,
        ac: AttackComplexity,
        pr: PrivilegesRequired,
        ui: UserInteraction,
        scope: Scope,
    ) -> float:
        """Calculate exploitability sub-score"""
        
        pr_value = self._metric_values[(pr, scope)]
        
        exploitability = (
            8.22 *
            self._metric_values[av] *
            self._metric_values[ac] *
            pr_value *
            self._metric_values[ui]
        )
        
        return exploitability

    def _round_up(self, score: float) -> float:
        """
        Round up to one decimal place per CVSS spec
        
        If the result is 0, return 0.0. Otherwise:
        - Round up to 1 decimal place
        - Smallest value > 0 is 0.1
        """
        if score <= 0:
            return 0.0
        
        int_score = int(score * 100000)
        
        if int_score % 10000 == 0:
            return float(int_score // 10000) / 10.0
        else:
            return float(int_score // 10000 + 1) / 10.0

    def _get_severity(self, base_score: float) -> str:
        """Get severity rating from base score"""
        if base_score == 0.0:
            return "NONE"
        elif base_score < 4.0:
            return "LOW"
        elif base_score < 7.0:
            return "MEDIUM"
        elif base_score < 9.0:
            return "HIGH"
        else:
            return "CRITICAL"

    def _build_vector_string(
        self,
        av: AttackVector,
        ac: AttackComplexity,
        pr: PrivilegesRequired,
        ui: UserInteraction,
        s: Scope,
        c: ImpactMetric,
        i: ImpactMetric,
        a: ImpactMetric,
    ) -> str:
        """Build CVSS v3.1 vector string"""
        return (
            f"CVSS:3.1/"
            f"AV:{av.value}/"
            f"AC:{ac.value}/"
            f"PR:{pr.value}/"
            f"UI:{ui.value}/"
            f"S:{s.value}/"
            f"C:{c.value}/"
            f"I:{i.value}/"
            f"A:{a.value}"
        )

    def parse_vector(self, vector_string: str) -> Optional[CVSSScore]:
        """
        Parse CVSS vector string and calculate score
        
        Args:
            vector_string: CVSS v3.1 vector (e.g., "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H")
        
        Returns:
            CVSSScore if valid, None if parsing fails
        """
        try:
            if not vector_string.startswith("CVSS:3."):
                logger.error(f"Invalid CVSS version in vector: {vector_string}")
                return None
            
            parts = vector_string.split("/")[1:]
            metrics = {}
            
            for part in parts:
                key, value = part.split(":")
                metrics[key] = value
            
            av = AttackVector(metrics["AV"])
            ac = AttackComplexity(metrics["AC"])
            pr = PrivilegesRequired(metrics["PR"])
            ui = UserInteraction(metrics["UI"])
            s = Scope(metrics["S"])
            c = ImpactMetric(metrics["C"])
            i = ImpactMetric(metrics["I"])
            a = ImpactMetric(metrics["A"])
            
            return self.calculate(av, ac, pr, ui, s, c, i, a)
        
        except Exception as e:
            logger.error(f"Error parsing CVSS vector '{vector_string}': {e}")
            return None


def quick_cvss(
    network: bool = True,
    easy: bool = True,
    no_auth: bool = True,
    no_interaction: bool = True,
    high_impact: bool = True,
) -> CVSSScore:
    """
    Quick CVSS calculation with common defaults
    
    Args:
        network: Network accessible (vs local)
        easy: Low complexity attack (vs high)
        no_auth: No authentication required (vs required)
        no_interaction: No user interaction (vs required)
        high_impact: High impact on CIA (vs low)
    
    Returns:
        Calculated CVSS score
    """
    calculator = CVSSCalculator()
    
    av = AttackVector.NETWORK if network else AttackVector.LOCAL
    ac = AttackComplexity.LOW if easy else AttackComplexity.HIGH
    pr = PrivilegesRequired.NONE if no_auth else PrivilegesRequired.LOW
    ui = UserInteraction.NONE if no_interaction else UserInteraction.REQUIRED
    s = Scope.UNCHANGED
    impact = ImpactMetric.HIGH if high_impact else ImpactMetric.LOW
    
    return calculator.calculate(av, ac, pr, ui, s, impact, impact, impact)
