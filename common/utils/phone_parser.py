# common/utils/phone_parser.py

import os
import re
import urllib.parse
import logging
import random
import asyncio
import jmespath
from dataclasses import dataclass
from typing import List, Optional
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Page, Browser

from common.utils.request_utils import make_request

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# ===========================
# Data structure
# ===========================
@dataclass
class ExtractionResult:
    phone_numbers: List[str]
    viber_link: Optional[str] = None


# ===========================
# Domain-specific constants
# ===========================
OLX_PHONE_LINK = "https://www.olx.ua/api/v1/offers/{}/limited-phones/"
REAL_ESTATE_LVIV_UA_LINK = "https://www.real-estate.lviv.ua/en/ajax_show_phone_object/{}"
REQUEST_TIMEOUT = 30  # seconds

SKU_REGEX = re.compile(r'"sku":"(.*?)"')
TELEPHONE_REGEX_REAL_ESTATE = re.compile(r'tel:(.*?)\\u0022')
LUN_PHONE_REGEX = re.compile(r'"phones\\":\[\\"8(.*)\\"],\\"geoEntities')
RIELTOR_PHONE_REGEX = re.compile(r'"tel:(.*?)"')
FAKTOR24_PHONE_REGEX = re.compile(r'"tel:(.*?)" id="phoneDisplay"')

# ===========================
# ZenRows fallback
# ===========================
ZENROWS_API_KEY = os.getenv("ZENROWS_API_KEY", "YOUR_DEFAULT_KEY")
ZENROWS_ENDPOINT = "https://api.zenrows.com/v1/"


def parse_proxy(proxy_url: str):
    parsed = urllib.parse.urlparse(proxy_url)
    return {
        "server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}",
        "username": parsed.username,
        "password": parsed.password
    }


def fetch_with_zenrows(url: str, js_render: bool = True) -> str:
    """
    Synchronous fallback using ZenRows.
    """
    logger.info(f"[ZenRows fallback] GET {url}, js_render={js_render}")
    params = {
        "apikey": ZENROWS_API_KEY,
        "url": url,
        "premium_proxy": "false",
        "js_render": "true" if js_render else "false",
    }

    # Use our centralized request utility
    response = make_request(
        url=ZENROWS_ENDPOINT,
        method='get',
        params=params,
        timeout=REQUEST_TIMEOUT,
        retries=3
    )

    if not response:
        raise Exception(f"Failed to get response from ZenRows for URL: {url}")

    return response.text


# ===========================
# Bright Data pool
# ===========================
BRIGHTDATA_PROXIES = [
    'http://brd-customer-hl_668fd6e0-zone-datacenter_proxy1:7g6edg65pwp8@brd.superproxy.io:33335',
    'http://brd-customer-hl_668fd6e0-zone-datacenter_proxy2:y6ft4jxbcvjm@brd.superproxy.io:33335',
    'http://brd-customer-hl_668fd6e0-zone-datacenter_proxy3:c9swm7yi5xhd@brd.superproxy.io:33335'
]


# ===========================
# User agent
# ===========================
def get_random_desktop_user_agent() -> str:
    """Get a random desktop user agent."""
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.51 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.4 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:98.0) Gecko/20100101 Firefox/98.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.75 Safari/537.36"
    ]
    return random.choice(user_agents)


# ===========================
# Domain-Specific fallback parse
# ===========================
def _parse_real_estate_lviv(ad_link: str) -> ExtractionResult:
    logger.info("Parsing real-estate.lviv.ua data.")
    ad_id_part = ad_link.split("/")[-1].split("-")[0]
    link_ = REAL_ESTATE_LVIV_UA_LINK.format(ad_id_part)
    try:
        # Use centralized request utility
        response = make_request(link_, timeout=REQUEST_TIMEOUT, retries=3)
        if not response:
            return ExtractionResult([], None)

        matches = TELEPHONE_REGEX_REAL_ESTATE.findall(response.text)
        if matches:
            phones = [p.replace('(', '').replace(')', '').replace(' ', '') for p in matches]
            return ExtractionResult(phones, None)
        return ExtractionResult([], None)
    except Exception:
        logger.exception("Error fetching real-estate.lviv.ua phone link.")
        return ExtractionResult([], None)


def _parse_lun(html: str) -> ExtractionResult:
    logger.info("Parsing lun.ua content.")
    matches = LUN_PHONE_REGEX.findall(html)
    if matches:
        return ExtractionResult([matches[0]], None)
    return ExtractionResult([], None)


def _parse_rieltor(html: str) -> ExtractionResult:
    logger.info("Parsing rieltor.ua content.")
    telephones = RIELTOR_PHONE_REGEX.findall(html)
    if telephones:
        return ExtractionResult([telephones[0]], None)
    return ExtractionResult([], None)


def _parse_faktor24(html: str) -> ExtractionResult:
    logger.info("Parsing faktor24.com content.")
    telephones = FAKTOR24_PHONE_REGEX.findall(html)
    if telephones:
        return ExtractionResult([telephones[0]], None)
    return ExtractionResult([], None)


def _fallback_parse(html: str) -> ExtractionResult:
    logger.info("Fallback parse for unknown domain.")
    soup = BeautifulSoup(html, "lxml")
    phone_nums, viber_link = [], None

    container = soup.find("div", class_="offer-view-rieltor-action")
    if container:
        contacts = container.find("div", attrs={"data-jss": "ovContacts"})
        if contacts:
            for link_ in contacts.find_all("a"):
                href = link_.get("href")
                if href and href.startswith("tel:"):
                    phone_nums.append(href)
        viber_a = container.find("a", id=lambda x: x and "send-viber" in x)
        if viber_a:
            viber_link = viber_a.get("href")

    return ExtractionResult(phone_nums, viber_link)


# ===========================
# OLX phone fetch with JS fetch
# w/ fallback to extra bright data attempts if 400
# ===========================
async def olx_js_fetch_phone(page: Page, sku: str, attempts: int = 3) -> Optional[str]:
    """
    Attempts to fetch OLX phone data from the same page context up to `attempts`.
    If 400 => next attempt, if still fail => None
    """
    phone_url = OLX_PHONE_LINK.format(sku)
    logger.info(f"OLX phone fetch via JS: {phone_url}")
    for i in range(1, attempts + 1):
        try:
            js_script = f"""
            (async () => {{
                const resp = await fetch("{phone_url}");
                const status_ = resp.status;
                if (!resp.ok) {{
                  return {{ status: status_, data: null }};
                }}
                const jd = await resp.json();
                return {{ status: status_, data: jd }};
            }})();
            """
            result = await page.evaluate(js_script)
            if not result:
                logger.warning(f"Attempt {i}: No result from OLX fetch.")
                continue

            st = result.get("status", 0)
            if st == 400:
                logger.warning(f"OLX phone API => 400 on attempt {i}")
                if i == attempts:
                    return None
                else:
                    continue
            elif st != 200:
                logger.warning(f"OLX phone => {st}, returning None.")
                return None

            data_ = result.get("data", {})
            phone = jmespath.search("data.phones[0]", data_)
            return phone
        except Exception as e:
            logger.exception(f"OLX phone fetch error attempt {i}: {e}")
            if i == attempts:
                return None
    return None


async def olx_js_fetch_phone_via_proxies(browser: Browser, resource_url: str, sku: str) -> Optional[str]:
    """
    If normal OLX fetch fails, do 3 attempts with random bright data proxies.
    Each attempt => new context => fetch w/ same JS script
    """
    if not BRIGHTDATA_PROXIES:
        logger.warning("No bright data proxies available for OLX fallback.")
        return None

    for attempt_ in range(1, 4):
        random_proxy = random.choice(BRIGHTDATA_PROXIES)
        proxy_config = parse_proxy(random_proxy)
        logger.info(f"OLX phone fallback via bright data proxy attempt {attempt_} => {random_proxy}")
        try:
            ua = get_random_desktop_user_agent()
            context = await browser.new_context(
                user_agent=ua,
                java_script_enabled=True,
                proxy=proxy_config
            )
            page = await context.new_page()
            await page.goto(resource_url, wait_until="networkidle", timeout=REQUEST_TIMEOUT * 1000)
            phone = await olx_js_fetch_phone(page, sku, attempts=1)
            await context.close()
            if phone:
                logger.info(f"Success with bright data proxy => {phone}")
                return phone
        except Exception as e:
            logger.exception(f"Proxy fallback attempt {attempt_} => error: {e}")
    logger.warning("All proxy fallback attempts for OLX phone => fail.")
    return None


async def parse_olx_playwright(html: str, page: Page, browser: Browser, resource_url: str) -> ExtractionResult:
    """
    1) parse HTML => find SKU
    2) attempt phone fetch in same page context
    3) if still fail => bright data fallback
    """
    if "It seems like a dead end" in html:
        logger.info("OLX indicates ad is no longer available.")
        return ExtractionResult([], None)

    match = SKU_REGEX.findall(html)
    if not match:
        logger.warning("No SKU found in OLX content.")
        return ExtractionResult([], None)

    sku = match[0]
    logger.info(f"Parsed OLX SKU => {sku}")
    phone = await olx_js_fetch_phone(page, sku, attempts=3)
    if phone:
        logger.info(f"OLX phone => {phone}")
        return ExtractionResult([phone], None)

    # fallback => bright data
    phone_via_proxy = await olx_js_fetch_phone_via_proxies(browser, resource_url, sku)
    if phone_via_proxy:
        logger.info(f"OLX phone after bright data => {phone_via_proxy}")
        return ExtractionResult([phone_via_proxy], None)

    # final => no phone
    return ExtractionResult([], None)


# ===========================
# Main domain parse
# ===========================
async def _domain_parse_final(html: str, original_url: str, page: Page, browser: Browser) -> ExtractionResult:
    soup = BeautifulSoup(html, "lxml")
    canonical_tag = soup.find("link", rel="canonical")
    canonical_url = canonical_tag["href"] if canonical_tag else original_url
    if canonical_url == original_url:
        logger.warning("canonical_url == original_url")
        logger.warning(html)
    logger.info(f"Canonical for {original_url}: {canonical_url}")

    if "olx.ua" in canonical_url:
        return await parse_olx_playwright(html, page, browser, original_url)
    elif "real-estate.lviv.ua" in canonical_url:
        return _parse_real_estate_lviv(canonical_url)
    elif "rieltor.ua" in canonical_url:
        return _parse_rieltor(html)
    elif "lun.ua" in canonical_url:
        return _parse_lun(html)
    elif "faktor24.com" in canonical_url:
        return _parse_faktor24(html)
    else:
        logger.warning("Unknown domain => fallback parse.")
        return _fallback_parse(html)


# ===========================
# Page fetch
# ===========================
async def _playwright_fetch_page(url: str, browser: Browser, proxy: Optional[str], attempts: int = 3) -> str:
    """
    Up to `attempts` times, random UA. If fail => raise.
    """
    for i in range(1, attempts + 1):
        ua = get_random_desktop_user_agent()
        proxy_settings = None
        if proxy:
            logger.info(f"Using proxy => {proxy}")
            proxy_settings = {"server": proxy}

        logger.info(f"[Playwright] Attempt {i}/{attempts} for {url} with UA={ua}, proxy={bool(proxy)}")
        context = await browser.new_context(
            user_agent=ua,
            java_script_enabled=True,
            proxy=proxy_settings
        )
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="networkidle", timeout=REQUEST_TIMEOUT * 1000)
            content = await page.content()
            await context.close()
            return content
        except Exception as e:
            logger.exception(f"Attempt {i} error => {e}")
            await context.close()
            await asyncio.sleep(1)
    raise Exception(f"Failed to load {url} after {attempts} attempts, proxy={proxy}")


# ===========================
# Async main fetch
# ===========================
async def _extract_phone_numbers_async(resource_url: str) -> ExtractionResult:
    """
    1) 3 attempts no-proxy
    2) 3 attempts random bright data proxies
    3) fallback ZenRows
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        # 1) no-proxy (3 attempts)
        try:
            html_np = await _playwright_fetch_page(resource_url, browser, None, attempts=5)
            # parse domain => need page context to do OLX phone
            ctx_np = await browser.new_context(java_script_enabled=True)
            page_np = await ctx_np.new_page()
            await page_np.goto(resource_url, wait_until="networkidle", timeout=REQUEST_TIMEOUT * 1000)
            result_np = await _domain_parse_final(html_np, resource_url, page_np, browser)
            await ctx_np.close()
            return result_np
        except Exception as e:
            logger.warning(f"No-proxy stage failed for {resource_url}. {e}")

        # 2) bright data proxies
        if BRIGHTDATA_PROXIES:
            logger.info("Trying bright data proxy approach (3 attempts, random from pool).")
            for att_ in range(1, 4):
                proxy_ = random.choice(BRIGHTDATA_PROXIES)
                try:
                    html_px = await _playwright_fetch_page(resource_url, browser, proxy_,
                                                           attempts=len(BRIGHTDATA_PROXIES))
                    ctx_px = await browser.new_context(java_script_enabled=True, proxy={"server": proxy_})
                    page_px = await ctx_px.new_page()
                    await page_px.goto(resource_url, wait_until="networkidle", timeout=REQUEST_TIMEOUT * 1000)
                    res_px = await _domain_parse_final(html_px, resource_url, page_px, browser)
                    await ctx_px.close()
                    return res_px
                except Exception:
                    logger.warning(f"Bright data attempt {att_} => fail for {proxy_}")
            logger.warning("All bright data attempts => fail.")
        else:
            logger.warning("No BRIGHTDATA_PROXY_POOL => skipping proxy stage.")

        # 3) fallback => ZenRows
        logger.info("Falling back to ZenRows approach.")
        try:
            zen_html = fetch_with_zenrows(resource_url, js_render=False)
            ctx_z = await browser.new_context(java_script_enabled=False)
            page_z = await ctx_z.new_page()  # not actually loaded => we'll parse offline
            res_z = await _domain_parse_final(zen_html, resource_url, page_z, browser)
            await ctx_z.close()
            return res_z
        except Exception:
            logger.exception("ZenRows fallback => error.")
            return ExtractionResult([], None)


def extract_phone_numbers_from_resource(resource_url: str) -> ExtractionResult:
    """
    Synchronous function:
      phones, viber = extract_phone_numbers_from_resource(url).phone_numbers, .viber_link
    """
    logger.info(f"extract_phone_numbers_from_resource => {resource_url}")
    try:
        return asyncio.run(_extract_phone_numbers_async(resource_url))
    except Exception:
        logger.exception("All final attempts => fail.")
        return ExtractionResult([], None)


if __name__ == "__main__":
    # example usage
    os.environ["BRIGHTDATA_PROXY_POOL"] = "http://user:pass@proxy1:port,http://user:pass@proxy2:port"
    test_urls = [
        "https://flatfy.ua/uk/redirect/2614567152",  # might cause OLX 400
        "https://flatfy.ua/uk/redirect/2614223824",  # might timeout
    ]
    for u in test_urls:
        result = extract_phone_numbers_from_resource(u)
        print(f"\nURL: {u}\nPhones: {result.phone_numbers}\nViber: {result.viber_link}")