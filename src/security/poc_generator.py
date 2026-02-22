"""
Proof-of-Concept (PoC) Exploit Generator
Generates safe, ethical exploit code for verified vulnerabilities
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from loguru import logger

from src.cognitive.llm.router import AIRouter
from src.security.ai_scanner import VulnerabilityFinding


class PoCLanguage(str, Enum):
    """PoC script languages"""
    PYTHON = "python"
    BASH = "bash"
    JAVASCRIPT = "javascript"
    CURL = "curl"


@dataclass
class PoCScript:
    """Generated proof-of-concept script"""
    language: str
    code: str
    description: str
    usage_instructions: str
    warnings: str


class PoCGenerator:
    """
    Proof-of-Concept exploit generator
    
    Features:
    - Safe exploit code generation
    - Multiple language support (Python, Bash, JS, curl)
    - WAF bypass techniques
    - Ethical warnings and disclaimers
    - Step-by-step execution instructions
    """

    ETHICAL_WARNING = """
    ⚠️  ETHICAL HACKING ONLY ⚠️
    
    This PoC is for AUTHORIZED security testing ONLY.
    
    ❌ DO NOT use against systems you don't own or have written permission to test.
    ❌ Unauthorized access is ILLEGAL and punishable by law.
    ✅ Only use on bug bounty programs, pentests, or your own systems.
    
    By using this PoC, you agree to follow responsible disclosure practices.
    """

    def __init__(self, ai_router: Optional[AIRouter] = None):
        """
        Initialize PoC generator
        
        Args:
            ai_router: AI router for code generation
        """
        self.ai_router = ai_router or AIRouter()

    async def generate_poc(
        self,
        finding: VulnerabilityFinding,
        language: PoCLanguage = PoCLanguage.PYTHON,
        include_waf_bypass: bool = False,
    ) -> PoCScript:
        """
        Generate PoC exploit code for vulnerability
        
        Args:
            finding: Vulnerability finding to exploit
            language: Programming language for PoC
            include_waf_bypass: Include WAF bypass techniques
        
        Returns:
            Generated PoC script with instructions
        """
        logger.info(f"Generating {language.value} PoC for {finding.title}")

        if language == PoCLanguage.CURL:
            return self._generate_curl_poc(finding, include_waf_bypass)
        elif language == PoCLanguage.BASH:
            return await self._generate_bash_poc(finding, include_waf_bypass)
        elif language == PoCLanguage.JAVASCRIPT:
            return await self._generate_js_poc(finding, include_waf_bypass)
        else:  # Python
            return await self._generate_python_poc(finding, include_waf_bypass)

    def _generate_curl_poc(
        self,
        finding: VulnerabilityFinding,
        include_waf_bypass: bool,
    ) -> PoCScript:
        """Generate curl command PoC"""
        
        url = finding.affected_url
        method = finding.http_method
        payload = finding.attack_vector
        
        headers = []
        if include_waf_bypass:
            headers.append('-H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)"')
            headers.append('-H "X-Forwarded-For: 127.0.0.1"')
        
        curl_cmd = f'curl -X {method} "{url}" \\\n'
        for header in headers:
            curl_cmd += f'  {header} \\\n'
        curl_cmd += '  -v'
        
        description = f"""
        Simple curl command to reproduce {finding.title}
        
        Vulnerability: {finding.description}
        Severity: {finding.severity}
        """
        
        usage = f"""
        1. Copy the curl command below
        2. Run in terminal: bash poc.sh
        3. Observe the response for evidence of vulnerability
        
        Expected result: {finding.evidence}
        """
        
        return PoCScript(
            language="curl",
            code=curl_cmd,
            description=description.strip(),
            usage_instructions=usage.strip(),
            warnings=self.ETHICAL_WARNING,
        )

    async def _generate_python_poc(
        self,
        finding: VulnerabilityFinding,
        include_waf_bypass: bool,
    ) -> PoCScript:
        """Generate Python PoC script using AI"""
        
        prompt = f"""
        Generate a Python proof-of-concept script for this vulnerability:
        
        Title: {finding.title}
        Description: {finding.description}
        URL: {finding.affected_url}
        Method: {finding.http_method}
        Parameter: {finding.vulnerable_parameter}
        Attack Vector: {finding.attack_vector}
        CWE: {finding.cwe_id}
        
        Requirements:
        1. Use 'requests' library
        2. Add detailed comments explaining each step
        3. Include error handling
        4. Print clear success/failure messages
        5. Make it safe (no destructive actions)
        {"6. Include WAF bypass techniques (headers, encoding)" if include_waf_bypass else ""}
        
        Format:
        ```python
        # [Python code here]
        ```
        
        Keep it simple, educational, and under 100 lines.
        """
        
        response = await self.ai_router.route_request(
            prompt=prompt,
            task_type="code_generation",
        )
        
        import re
        code_match = re.search(r'```python\n(.*?)```', response, re.DOTALL)
        code = code_match.group(1).strip() if code_match else response
        
        description = f"Python exploit for {finding.title}"
        
        usage = """
        1. Install dependencies: pip install requests
        2. Run script: python poc.py
        3. Review output for success indicators
        
        Modify TARGET_URL if needed.
        """
        
        return PoCScript(
            language="python",
            code=code,
            description=description,
            usage_instructions=usage.strip(),
            warnings=self.ETHICAL_WARNING,
        )

    async def _generate_bash_poc(
        self,
        finding: VulnerabilityFinding,
        include_waf_bypass: bool,
    ) -> PoCScript:
        """Generate Bash script PoC"""
        
        prompt = f"""
        Generate a Bash script proof-of-concept for this vulnerability:
        
        Title: {finding.title}
        URL: {finding.affected_url}
        Method: {finding.http_method}
        Attack Vector: {finding.attack_vector}
        
        Requirements:
        1. Use curl or wget
        2. Add comments
        3. Check if vulnerability exists
        4. Print clear results
        {"5. Add WAF bypass headers" if include_waf_bypass else ""}
        
        Format:
        ```bash
        # [Bash code here]
        ```
        
        Keep it under 50 lines.
        """
        
        response = await self.ai_router.route_request(
            prompt=prompt,
            task_type="code_generation",
        )
        
        import re
        code_match = re.search(r'```(?:bash|sh)\n(.*?)```', response, re.DOTALL)
        code = code_match.group(1).strip() if code_match else response
        
        description = f"Bash exploit for {finding.title}"
        
        usage = """
        1. Make executable: chmod +x poc.sh
        2. Run: ./poc.sh
        3. Check output for vulnerability confirmation
        """
        
        return PoCScript(
            language="bash",
            code=code,
            description=description,
            usage_instructions=usage.strip(),
            warnings=self.ETHICAL_WARNING,
        )

    async def _generate_js_poc(
        self,
        finding: VulnerabilityFinding,
        include_waf_bypass: bool,
    ) -> PoCScript:
        """Generate JavaScript PoC"""
        
        prompt = f"""
        Generate a JavaScript/Node.js proof-of-concept for this vulnerability:
        
        Title: {finding.title}
        URL: {finding.affected_url}
        Attack Vector: {finding.attack_vector}
        
        Requirements:
        1. Use fetch() or axios
        2. Browser or Node.js compatible
        3. Add comments
        4. Log results to console
        {"5. Include WAF bypass techniques" if include_waf_bypass else ""}
        
        Format:
        ```javascript
        // [JavaScript code here]
        ```
        
        Keep it under 80 lines.
        """
        
        response = await self.ai_router.route_request(
            prompt=prompt,
            task_type="code_generation",
        )
        
        import re
        code_match = re.search(r'```(?:javascript|js)\n(.*?)```', response, re.DOTALL)
        code = code_match.group(1).strip() if code_match else response
        
        description = f"JavaScript exploit for {finding.title}"
        
        usage = """
        Browser:
        1. Open browser console (F12)
        2. Paste code and press Enter
        
        Node.js:
        1. Install dependencies: npm install axios
        2. Run: node poc.js
        """
        
        return PoCScript(
            language="javascript",
            code=code,
            description=description,
            usage_instructions=usage.strip(),
            warnings=self.ETHICAL_WARNING,
        )

    def save_poc(self, poc: PoCScript, output_path: str) -> str:
        """
        Save PoC script to file
        
        Args:
            poc: Generated PoC script
            output_path: Where to save the file
        
        Returns:
            Path to saved file
        """
        extensions = {
            "python": ".py",
            "bash": ".sh",
            "javascript": ".js",
            "curl": ".sh",
        }
        
        if not output_path.endswith(extensions[poc.language]):
            output_path += extensions[poc.language]
        
        content = f"""#!/usr/bin/env {poc.language if poc.language != 'curl' else 'bash'}
{poc.warnings}

'''
{poc.description}

USAGE:
{poc.usage_instructions}
'''

{poc.code}
"""
        
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        
        logger.info(f"Saved PoC to {output_path}")
        return output_path
