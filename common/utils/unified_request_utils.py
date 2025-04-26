# common/utils/unified_request_utils.py

import logging
import requests
import time
import random
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Optional, Dict, Any, Union, List, Tuple

logger = logging.getLogger(__name__)

# Common constants
DEFAULT_TIMEOUT = 30
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF_FACTOR = 0.3
DEFAULT_STATUS_FORCELIST = (500, 502, 504)

# Default headers for HTTP requests
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:134.0) Gecko/20100101 Firefox/134.0",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br, zstd",
}

# API base URLs
BASE_FLATFY_URL = "https://flatfy.ua/api/realties"


def get_retry_session(
        retries: int = DEFAULT_RETRIES,
        backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
        status_forcelist: tuple = DEFAULT_STATUS_FORCELIST,
        session: Optional[requests.Session] = None,
) -> requests.Session:
    """
    Get requests session with retry configuration.

    Args:
        retries: Number of retries
        backoff_factor: Backoff factor for retries
        status_forcelist: HTTP status codes to retry on
        session: Existing session to configure (creates new if None)

    Returns:
        Configured requests session
    """
    session = session or requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS"]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session


def make_request(
        url: str,
        method: str = 'get',
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Union[float, tuple] = DEFAULT_TIMEOUT,
        retries: int = DEFAULT_RETRIES,
        session: Optional[requests.Session] = None,
        jitter: bool = True,
        raise_for_status: bool = True
) -> Optional[requests.Response]:
    """
    Make HTTP request with retries and proper error handling

    Args:
        url: Request URL
        method: HTTP method (get, post, put, delete)
        params: URL parameters
        data: Form data
        json: JSON data
        headers: HTTP headers
        timeout: Request timeout in seconds
        retries: Number of retries
        session: Existing session to use
        jitter: Whether to add jitter to retry delays
        raise_for_status: Whether to raise exception on HTTP error

    Returns:
        Response object or None if error and raise_for_status=False
    """
    session = get_retry_session(retries=retries, session=session)

    # Create default headers if none provided
    if not headers:
        headers = DEFAULT_HEADERS.copy()

    method = method.lower()

    try:
        logger.debug(f"Making {method.upper()} request to {url}")

        if method == 'get':
            response = session.get(url, params=params, headers=headers, timeout=timeout)
        elif method == 'post':
            response = session.post(url, params=params, data=data, json=json, headers=headers, timeout=timeout)
        elif method == 'put':
            response = session.put(url, params=params, data=data, json=json, headers=headers, timeout=timeout)
        elif method == 'delete':
            response = session.delete(url, params=params, data=data, json=json, headers=headers, timeout=timeout)
        else:
            logger.error(f"Unsupported HTTP method: {method}")
            raise ValueError(f"Unsupported HTTP method: {method}")

        if raise_for_status:
            response.raise_for_status()

        return response

    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP Error: {e} for URL: {url}")
        if raise_for_status:
            raise
        return None
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection Error: {e} for URL: {url}")
        if raise_for_status:
            raise
        return None
    except requests.exceptions.Timeout as e:
        logger.error(f"Timeout Error: {e} for URL: {url}")
        if raise_for_status:
            raise
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Request Error: {e} for URL: {url}")
        if raise_for_status:
            raise
        return None


def fetch_with_retry(
        url: str,
        method: str = 'get',
        max_retries: int = DEFAULT_RETRIES,
        retry_delay: float = DEFAULT_BACKOFF_FACTOR,
        retry_status_codes: tuple = DEFAULT_STATUS_FORCELIST,
        **kwargs
) -> Optional[requests.Response]:
    """
    Fetch with retry logic but simpler interface than make_request.

    Args:
        url: URL to fetch
        method: HTTP method (get, post, etc.)
        max_retries: Maximum number of retries
        retry_delay: Initial delay between retries
        retry_status_codes: Status codes to retry on
        **kwargs: Additional arguments to pass to requests

    Returns:
        Response object or None if all retries fail
    """
    for attempt in range(max_retries + 1):
        try:
            if method.lower() == 'get':
                response = requests.get(url, **kwargs)
            elif method.lower() == 'post':
                response = requests.post(url, **kwargs)
            elif method.lower() == 'put':
                response = requests.put(url, **kwargs)
            elif method.lower() == 'delete':
                response = requests.delete(url, **kwargs)
            else:
                logger.error(f"Unsupported HTTP method: {method}")
                return None

            response.raise_for_status()
            return response

        except (requests.exceptions.RequestException) as e:
            if attempt < max_retries:
                # Calculate delay with exponential backoff and jitter
                delay = retry_delay * (2 ** attempt)
                delay *= random.uniform(0.8, 1.2)  # Add jitter

                logger.warning(
                    f"Request failed (attempt {attempt + 1}/{max_retries + 1}): {e}. "
                    f"Retrying in {delay:.2f}s"
                )
                time.sleep(delay)
            else:
                logger.error(f"Request failed after {max_retries + 1} attempts: {e}")
                return None


# ===== API-Specific Utility Functions =====

def fetch_ads_flatfy(
        geo_id=None,
        page=1,
        room_count=None,
        price_min=None,
        price_max=None,
        section_id=2,
        # Additional optional params:
        currency="UAH",
        group_collapse="1",
        has_eoselia="false",
        is_without_fee="false",
        lang="uk",
        price_sqm_currency="UAH",
        sort="insert_time"
) -> list:
    """
    Fetch a list of ad dicts from flatfy.ua API with shared logic.

    Args:
      geo_id (int|None): The city geo_id, e.g. from your GEO_ID_MAPPING.
      page (int): Page number to fetch.
      room_count (list|None): e.g. [1,2] or None.
      price_min (int|None): If set, filter ads with price >= price_min.
      price_max (int|None): If set, filter ads with price <= price_max.
      section_id (int): e.g. 2 for apartments, 4 for houses, etc.
      ...

    Returns:
      list: A list of ad dictionaries or empty list if error or none.
    """
    try:
        params = {
            "geo_id": geo_id,
            "page": page,
            "section_id": section_id,
            "currency": currency,
            "group_collapse": group_collapse,
            "has_eoselia": has_eoselia,
            "is_without_fee": is_without_fee,
            "lang": lang,
            "price_sqm_currency": price_sqm_currency,
            "sort": sort,
        }

        if room_count:
            params["room_count"] = room_count
        if price_min is not None:
            params["price_min"] = str(price_min)
        if price_max is not None:
            params["price_max"] = str(price_max)

        logger.info(f"Fetching Flatfy ads with params: {params}")

        # Use our make_request utility
        response = make_request(
            BASE_FLATFY_URL,
            method='get',
            params=params,
            headers=DEFAULT_HEADERS,
            timeout=15,
            retries=3
        )

        if response is None or response.status_code != 200:
            logger.error(f"Fetch failed with status {response.status_code if response else 'No response'}.")
            return []

        data = response.json().get("data", [])
        logger.info(f"Received {len(data)} ads from Flatfy.")
        return data
    except Exception as e:
        logger.error(f"Failed to fetch ads from Flatfy: {e}")
        return []


# ===== Convenience Wrappers =====

def get_json(url: str, **kwargs) -> Optional[Dict[str, Any]]:
    """
    Convenience wrapper to make a GET request and return JSON data.

    Args:
        url: URL to fetch
        **kwargs: Additional arguments to pass to make_request

    Returns:
        JSON data as dictionary or None if request failed
    """
    response = make_request(url, method='get', **kwargs)
    if response and response.status_code == 200:
        try:
            return response.json()
        except ValueError as e:
            logger.error(f"Failed to parse JSON response: {e}")
    return None


def post_json(url: str, data: Dict[str, Any], **kwargs) -> Optional[Dict[str, Any]]:
    """
    Convenience wrapper to make a POST request with JSON data and return JSON response.

    Args:
        url: URL to post to
        data: JSON data to send
        **kwargs: Additional arguments to pass to make_request

    Returns:
        JSON response as dictionary or None if request failed
    """
    response = make_request(url, method='post', json=data, **kwargs)
    if response and response.status_code in (200, 201, 202):
        try:
            return response.json()
        except ValueError as e:
            logger.error(f"Failed to parse JSON response: {e}")
    return None


def download_file(url: str, local_path: str, **kwargs) -> bool:
    """
    Download a file from a URL to a local path.

    Args:
        url: URL of the file to download
        local_path: Local path to save the file to
        **kwargs: Additional arguments to pass to make_request

    Returns:
        True if download was successful, False otherwise
    """
    # Set stream=True to avoid loading the whole file into memory
    kwargs['stream'] = True

    response = make_request(url, **kwargs)
    if not response:
        return False

    try:
        with open(local_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        logger.error(f"Failed to save downloaded file to {local_path}: {e}")
        return False