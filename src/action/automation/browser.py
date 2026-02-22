"""
Browser Automation with Playwright

Features:
- Multi-browser support (Chromium, Firefox, WebKit)
- Form filling and interaction
- Data extraction
- Screenshot and PDF capture
- Network interception
- Headless or visible mode
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4


class BrowserType(str, Enum):
    CHROMIUM = "chromium"
    FIREFOX = "firefox"
    WEBKIT = "webkit"


class WaitCondition(str, Enum):
    LOAD = "load"
    DOMCONTENTLOADED = "domcontentloaded"
    NETWORKIDLE = "networkidle"


@dataclass
class BrowserContext:
    """Browser context configuration"""
    viewport_width: int = 1920
    viewport_height: int = 1080
    user_agent: Optional[str] = None
    locale: str = "en-US"
    timezone: str = "America/New_York"
    permissions: List[str] = field(default_factory=list)
    geolocation: Optional[Dict[str, float]] = None
    extra_http_headers: Dict[str, str] = field(default_factory=dict)


@dataclass
class NavigationResult:
    """Result from navigation"""
    url: str
    title: str
    status_code: int
    load_time: float
    screenshot: Optional[bytes] = None


@dataclass
class FormField:
    """Form field definition"""
    selector: str
    value: str
    field_type: str = "input"


@dataclass
class ExtractionRule:
    """Data extraction rule"""
    name: str
    selector: str
    attribute: Optional[str] = None
    multiple: bool = False


class BrowserAutomation:
    """
    Browser automation using Playwright
    
    Features:
    - Navigate to URLs
    - Fill forms
    - Click elements
    - Extract data
    - Handle popups and alerts
    - Take screenshots
    """
    
    def __init__(
        self,
        browser_type: BrowserType = BrowserType.CHROMIUM,
        headless: bool = True,
        context_config: Optional[BrowserContext] = None,
    ):
        self.browser_type = browser_type
        self.headless = headless
        self.context_config = context_config or BrowserContext()
        
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        
        self._action_log: List[dict] = []
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()
    
    async def start(self):
        """Start browser"""
        try:
            from playwright.async_api import async_playwright
            
            self._playwright = await async_playwright().start()
            
            if self.browser_type == BrowserType.CHROMIUM:
                self._browser = await self._playwright.chromium.launch(headless=self.headless)
            elif self.browser_type == BrowserType.FIREFOX:
                self._browser = await self._playwright.firefox.launch(headless=self.headless)
            elif self.browser_type == BrowserType.WEBKIT:
                self._browser = await self._playwright.webkit.launch(headless=self.headless)
            
            context_options = {
                "viewport": {
                    "width": self.context_config.viewport_width,
                    "height": self.context_config.viewport_height,
                },
                "locale": self.context_config.locale,
                "timezone_id": self.context_config.timezone,
            }
            
            if self.context_config.user_agent:
                context_options["user_agent"] = self.context_config.user_agent
            
            if self.context_config.geolocation:
                context_options["geolocation"] = self.context_config.geolocation
                context_options["permissions"] = ["geolocation"]
            
            if self.context_config.extra_http_headers:
                context_options["extra_http_headers"] = self.context_config.extra_http_headers
            
            self._context = await self._browser.new_context(**context_options)
            self._page = await self._context.new_page()
            
        except ImportError:
            raise ImportError(
                "Playwright not installed. "
                "Install with: pip install playwright && playwright install"
            )
    
    async def close(self):
        """Close browser"""
        if self._page:
            await self._page.close()
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
    
    def _log_action(self, action: str, params: dict):
        """Log browser action"""
        self._action_log.append({
            "id": str(uuid4()),
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "params": params,
        })
    
    async def navigate(
        self,
        url: str,
        wait_until: WaitCondition = WaitCondition.LOAD,
        timeout: float = 30.0,
        take_screenshot: bool = False,
    ) -> NavigationResult:
        """
        Navigate to URL
        
        Args:
            url: URL to navigate to
            wait_until: Wait condition
            timeout: Navigation timeout (seconds)
            take_screenshot: Capture screenshot after load
        """
        if not self._page:
            raise RuntimeError("Browser not started. Call start() first.")
        
        self._log_action("navigate", {"url": url})
        
        start_time = datetime.now()
        
        response = await self._page.goto(
            url,
            wait_until=wait_until.value,
            timeout=int(timeout * 1000),
        )
        
        load_time = (datetime.now() - start_time).total_seconds()
        
        title = await self._page.title()
        
        screenshot = None
        if take_screenshot:
            screenshot = await self._page.screenshot(full_page=True)
        
        return NavigationResult(
            url=self._page.url,
            title=title,
            status_code=response.status if response else 0,
            load_time=load_time,
            screenshot=screenshot,
        )
    
    async def click(
        self,
        selector: str,
        timeout: float = 10.0,
    ) -> bool:
        """Click element by selector"""
        if not self._page:
            raise RuntimeError("Browser not started")
        
        self._log_action("click", {"selector": selector})
        
        try:
            await self._page.click(
                selector,
                timeout=int(timeout * 1000),
            )
            return True
        except Exception as e:
            print(f"Click failed: {e}")
            return False
    
    async def fill_form(
        self,
        fields: List[FormField],
        timeout: float = 10.0,
    ) -> bool:
        """
        Fill form fields
        
        Args:
            fields: List of form fields to fill
            timeout: Timeout per field
        """
        if not self._page:
            raise RuntimeError("Browser not started")
        
        self._log_action("fill_form", {"field_count": len(fields)})
        
        try:
            for field in fields:
                if field.field_type == "input":
                    await self._page.fill(
                        field.selector,
                        field.value,
                        timeout=int(timeout * 1000),
                    )
                elif field.field_type == "select":
                    await self._page.select_option(
                        field.selector,
                        field.value,
                        timeout=int(timeout * 1000),
                    )
                elif field.field_type == "checkbox":
                    await self._page.check(
                        field.selector,
                        timeout=int(timeout * 1000),
                    )
            
            return True
        except Exception as e:
            print(f"Fill form failed: {e}")
            return False
    
    async def extract_data(
        self,
        rules: List[ExtractionRule],
    ) -> Dict[str, Any]:
        """
        Extract data from page
        
        Args:
            rules: List of extraction rules
        """
        if not self._page:
            raise RuntimeError("Browser not started")
        
        self._log_action("extract_data", {"rule_count": len(rules)})
        
        data = {}
        
        for rule in rules:
            try:
                if rule.multiple:
                    elements = await self._page.query_selector_all(rule.selector)
                    values = []
                    for element in elements:
                        if rule.attribute:
                            value = await element.get_attribute(rule.attribute)
                        else:
                            value = await element.text_content()
                        values.append(value)
                    data[rule.name] = values
                else:
                    element = await self._page.query_selector(rule.selector)
                    if element:
                        if rule.attribute:
                            value = await element.get_attribute(rule.attribute)
                        else:
                            value = await element.text_content()
                        data[rule.name] = value
            except Exception as e:
                print(f"Extraction failed for {rule.name}: {e}")
                data[rule.name] = None
        
        return data
    
    async def wait_for_selector(
        self,
        selector: str,
        timeout: float = 10.0,
        visible: bool = True,
    ) -> bool:
        """Wait for element to appear"""
        if not self._page:
            raise RuntimeError("Browser not started")
        
        try:
            await self._page.wait_for_selector(
                selector,
                timeout=int(timeout * 1000),
                state="visible" if visible else "attached",
            )
            return True
        except:
            return False
    
    async def evaluate_javascript(
        self,
        script: str,
    ) -> Any:
        """Execute JavaScript in page context"""
        if not self._page:
            raise RuntimeError("Browser not started")
        
        self._log_action("evaluate_js", {"script": script[:100]})
        
        try:
            result = await self._page.evaluate(script)
            return result
        except Exception as e:
            print(f"JavaScript evaluation failed: {e}")
            return None
    
    async def screenshot(
        self,
        full_page: bool = True,
        path: Optional[Path] = None,
    ) -> bytes:
        """Take screenshot"""
        if not self._page:
            raise RuntimeError("Browser not started")
        
        self._log_action("screenshot", {"full_page": full_page})
        
        screenshot_bytes = await self._page.screenshot(
            full_page=full_page,
            path=str(path) if path else None,
        )
        
        return screenshot_bytes
    
    async def pdf(
        self,
        path: Optional[Path] = None,
        format: str = "A4",
    ) -> bytes:
        """Generate PDF of page"""
        if not self._page:
            raise RuntimeError("Browser not started")
        
        self._log_action("pdf", {"format": format})
        
        pdf_bytes = await self._page.pdf(
            path=str(path) if path else None,
            format=format,
        )
        
        return pdf_bytes
    
    async def get_cookies(self) -> List[Dict[str, Any]]:
        """Get all cookies"""
        if not self._context:
            raise RuntimeError("Browser not started")
        
        return await self._context.cookies()
    
    async def set_cookie(
        self,
        name: str,
        value: str,
        domain: Optional[str] = None,
        path: str = "/",
    ):
        """Set cookie"""
        if not self._context:
            raise RuntimeError("Browser not started")
        
        cookie = {
            "name": name,
            "value": value,
            "path": path,
        }
        
        if domain:
            cookie["domain"] = domain
        else:
            cookie["url"] = self._page.url
        
        await self._context.add_cookies([cookie])
    
    async def clear_cookies(self):
        """Clear all cookies"""
        if not self._context:
            raise RuntimeError("Browser not started")
        
        await self._context.clear_cookies()
    
    async def handle_dialog(
        self,
        accept: bool = True,
        prompt_text: Optional[str] = None,
    ):
        """Handle alert/confirm/prompt dialogs"""
        if not self._page:
            raise RuntimeError("Browser not started")
        
        def dialog_handler(dialog):
            if accept:
                if prompt_text and dialog.type == "prompt":
                    asyncio.create_task(dialog.accept(prompt_text))
                else:
                    asyncio.create_task(dialog.accept())
            else:
                asyncio.create_task(dialog.dismiss())
        
        self._page.on("dialog", dialog_handler)
    
    async def intercept_network(
        self,
        url_pattern: str,
        response_body: Optional[str] = None,
        status_code: int = 200,
    ):
        """Intercept network requests"""
        if not self._page:
            raise RuntimeError("Browser not started")
        
        async def route_handler(route):
            if response_body:
                await route.fulfill(
                    status=status_code,
                    body=response_body,
                )
            else:
                await route.continue_()
        
        await self._page.route(url_pattern, route_handler)
    
    def get_action_log(self) -> List[dict]:
        """Get all logged actions"""
        return self._action_log.copy()
