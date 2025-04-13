# common/utils/req_utils.py
import logging
from common.utils.request_utils import make_request

logger = logging.getLogger(__name__)

BASE_FLATFY_URL = "https://flatfy.ua/api/realties"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:134.0) Gecko/20100101 Firefox/134.0",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br, zstd",
}


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

        # Use our new make_request utility instead of direct requests call
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