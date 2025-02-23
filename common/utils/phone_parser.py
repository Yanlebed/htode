import os
import logging
import re
import json
import jmespath
import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import List, Optional
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---------------------------
# Configuration & Constants
# ---------------------------

# Read sensitive configuration from environment variables
ZENROWS_API_KEY = os.getenv("ZENROWS_API_KEY", "a5087ace5e20caa2bf41149f93e308fddee387b1")
ZENROWS_ENDPOINT = "https://api.zenrows.com/v1/"

# Domain-specific URL templates
OLX_PHONE_LINK = "https://www.olx.ua/api/v1/offers/{}/limited-phones/"
REAL_ESTATE_LVIV_UA_LINK = "https://www.real-estate.lviv.ua/en/ajax_show_phone_object/{}"

# Request timeout
REQUEST_TIMEOUT = 30

# ---------------------------
# Logging Configuration
# ---------------------------

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ---------------------------
# Precompiled Regular Expressions
# ---------------------------

SKU_REGEX = re.compile(r'"sku":"(.*?)"')
REDIRECT_LINK_REGEX = re.compile(r'a class="redirect-link" href="(.*?)"')
TELEPHONE_REGEX_REAL_ESTATE = re.compile(r'tel:(.*?)\\u0022')
LUN_PHONE_REGEX = re.compile(r'"phones\\":\[\\"8(.*)\\"],\\"geoEntities')
RIELTOR_PHONE_REGEX = re.compile(r'"tel:(.*?)"')
FAKTOR24_PHONE_REGEX = re.compile(r'"tel:(.*?)" id="phoneDisplay"')


# ---------------------------
# Data Class for Results
# ---------------------------

@dataclass
class ExtractionResult:
    phone_numbers: List[str]
    viber_link: Optional[str] = None


# ---------------------------
# Requests Session with Retries
# ---------------------------

def get_requests_session() -> requests.Session:
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


session = get_requests_session()


# ---------------------------
# Helper Functions
# ---------------------------

def fetch_with_zenrows(url: str, js_render: bool = True) -> str:
    """
    Fetch HTML content from a URL using the ZenRows API.
    """
    logger.info(f"[ZenRows] Fetching {url} with js_render={js_render}")
    params = {
        "apikey": ZENROWS_API_KEY,
        "url": url,
        "premium_proxy": "false",
        "js_render": "true" if js_render else "false",
    }
    try:
        resp = session.get(ZENROWS_ENDPOINT, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.exception(f"Error fetching URL via ZenRows: {url}")
        raise e
    return resp.text


def _extract_redirect_link(html: str) -> Optional[str]:
    """
    Extracts the first redirect link from HTML using a regex pattern.
    """
    matches = REDIRECT_LINK_REGEX.findall(html)
    return matches[0] if matches else None


# ---------------------------
# Domain-Specific Processors
# ---------------------------

def _process_olx_redirect(response_text: str) -> ExtractionResult:
    """
    Processes OLX pages by extracting the SKU and then fetching the phone data.
    """
    logger.info("Processing OLX redirect page content.")
    if "It seems like a dead end" in response_text:
        logger.info("OLX indicates the ad is no longer available.")
        return ExtractionResult(phone_numbers=[])

    sku_matches = SKU_REGEX.findall(response_text)
    if not sku_matches:
        logger.info("SKU not found in OLX response.")
        return ExtractionResult(phone_numbers=[])

    ad_sku = sku_matches[0]
    olx_api_url = OLX_PHONE_LINK.format(ad_sku)
    logger.info(f"OLX SKU: {ad_sku}, fetching phone API at {olx_api_url}")

    try:
        api_response = fetch_with_zenrows(olx_api_url, js_render=False)
        data_json = json.loads(api_response)
        phone_number = jmespath.search("data.phones[0]", data_json)
        if phone_number:
            logger.info(f"Found OLX phone: {phone_number}")
            return ExtractionResult(phone_numbers=[phone_number])
        else:
            logger.info("No phone found in OLX JSON response.")
            return ExtractionResult(phone_numbers=[])
    except requests.exceptions.RequestException:
        logger.exception("Error fetching OLX phone API.")
        return ExtractionResult(phone_numbers=[])
    except Exception:
        logger.exception("Unexpected error processing OLX redirect.")
        return ExtractionResult(phone_numbers=[])


def _process_real_estate_lviv(ad_link: str) -> ExtractionResult:
    """
    Extracts phone numbers from real-estate.lviv.ua pages using regex.
    """
    logger.info("Processing real-estate.lviv.ua data.")
    real_estate_lviv_ad_id = ad_link.split("/")[-1].split("-")[0]
    r_e_phone_link = REAL_ESTATE_LVIV_UA_LINK.format(real_estate_lviv_ad_id)
    try:
        resp = session.get(r_e_phone_link, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.exceptions.RequestException:
        logger.exception(f"Error fetching real-estate.lviv.ua URL: {r_e_phone_link}")
        return ExtractionResult(phone_numbers=[])

    phone_matches = TELEPHONE_REGEX_REAL_ESTATE.findall(resp.text)
    if phone_matches:
        result = [el.replace('(', '').replace(')', '').replace(' ', '') for el in phone_matches]
        logger.info(f"Found real-estate.lviv.ua phones: {result}")
        return ExtractionResult(phone_numbers=result)
    else:
        logger.info("No phone found in real-estate.lviv.ua response.")
        return ExtractionResult(phone_numbers=[])


def _process_lun(response_text: str) -> ExtractionResult:
    """
    Extracts phone numbers from lun.ua pages using regex.
    """
    logger.info("Processing lun.ua page content.")
    matches = LUN_PHONE_REGEX.findall(response_text)
    if matches:
        final_phone = matches[0]
        logger.info(f"Found lun.ua phone: {final_phone}")
        return ExtractionResult(phone_numbers=[final_phone])
    else:
        logger.info("No phone numbers found in lun.ua response.")
        return ExtractionResult(phone_numbers=[])


def _process_rieltor(response_text: str) -> ExtractionResult:
    """
    Processes rieltor.ua pages (stub implementation) to extract phone numbers.
    """
    logger.info("Processing rieltor.ua page content.")
    telephone_data = RIELTOR_PHONE_REGEX.findall(response_text)
    if telephone_data:
        logger.info(f"Found rieltor.ua phone: {telephone_data[0]}")
        return ExtractionResult(phone_numbers=[telephone_data[0]])
    else:
        logger.info("No phone numbers found in rieltor.ua response.")
        return ExtractionResult(phone_numbers=[])

def _process_faktor24(response_text: str) -> ExtractionResult:
    logger.info("Processing faktor24.com page content.")
    telephone_data = FAKTOR24_PHONE_REGEX.findall(response_text)
    if telephone_data:
        logger.info(f"Found faktor24.com phone: {telephone_data[0]}")
        return ExtractionResult(phone_numbers=[telephone_data[0]])
    else:
        logger.info("No phone numbers found in faktor24.com response.")
        return ExtractionResult(phone_numbers=[])


# ---------------------------
# Main Extraction Function
# ---------------------------

def extract_phone_numbers_from_resource(resource_url: str) -> ExtractionResult:
    """
    Fetches a resource URL via ZenRows and extracts phone numbers using
    domain-specific logic. Falls back to BeautifulSoup parsing if the domain
    is unknown.

    Args:
        resource_url (str): The initial URL to fetch.

    Returns:
        ExtractionResult: An object containing a list of phone numbers and
                          an optional Viber link.
    """
    logger.info(f"[ZenRows] extract_phone_numbers_from_resource -> {resource_url}")
    try:
        html_content = fetch_with_zenrows(resource_url, js_render=False)
    except Exception:
        logger.exception(f"ZenRows request failed for {resource_url}")
        return ExtractionResult(phone_numbers=[])

    redirect_link = _extract_redirect_link(html_content)
    if redirect_link:
        logger.info(f"Redirect link found: {redirect_link}")
        try:
            html_content = fetch_with_zenrows(redirect_link, js_render=False)
        except Exception:
            logger.exception(f"ZenRows request failed for redirect link: {redirect_link}")
            return ExtractionResult(phone_numbers=[])
    else:
        logger.info(f"No redirect link found for resource_url: {resource_url}")

    # Domain-specific extraction based on known patterns in HTML or redirect URL.
    if "olx.ua" in html_content:
        logger.info("Detected OLX domain.")
        return _process_olx_redirect(html_content)
    elif "real-estate.lviv.ua" in html_content:
        logger.info("Detected real-estate.lviv.ua domain.")
        return _process_real_estate_lviv(redirect_link if redirect_link else resource_url)
    elif "rieltor.ua" in html_content and redirect_link and "rieltor.ua" in redirect_link:
        logger.info("Detected rieltor.ua domain.")
        return _process_rieltor(html_content)
    elif "lun.ua" in html_content and redirect_link and "lun.ua" in redirect_link:
        logger.info("Detected lun.ua domain.")
        return _process_lun(html_content)
    elif "faktor24.com" in redirect_link:
        logger.info("Detected faktor24.com domain.")
        return _process_faktor24(html_content)
    else:
        logger.warning("Unknown domain. Attempting fallback parse with BeautifulSoup.")
        soup = BeautifulSoup(html_content, "lxml")
        phone_numbers = []
        viber_link = None
        container = soup.find("div", class_="offer-view-rieltor-action")
        if container:
            contacts = container.find("div", attrs={"data-jss": "ovContacts"})
            if contacts:
                for link_ in contacts.find_all("a"):
                    href = link_.get("href")
                    if href and href.startswith("tel:"):
                        phone_numbers.append(href)
            viber_a = container.find("a", id=lambda x: x and "send-viber" in x)
            if viber_a:
                viber_link = viber_a.get("href")
        return ExtractionResult(phone_numbers=phone_numbers, viber_link=viber_link)
