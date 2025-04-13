# common/utils/request_utils.py

import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Optional, Dict, Any, Union

logger = logging.getLogger(__name__)


def get_retry_session(
        retries: int = 3,
        backoff_factor: float = 0.3,
        status_forcelist: tuple = (500, 502, 504),
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
        timeout: Union[float, tuple] = 30,
        retries: int = 3,
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
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:134.0) Gecko/20100101 Firefox/134.0",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br, zstd",
        }

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