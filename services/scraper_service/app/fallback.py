import aiohttp
from common.utils.proxies import get_user_agent
from common.utils.logger import logger


def fetch_with_fallback():
    # Пример простого fallback: 2-3 попытки
    for attempt in range(3):
        try:
            return fetch_once()
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1} failed: {e}")
    return None


async def fetch_once():
    url = "https://example.com/api/realties"
    headers = {"User-Agent": get_user_agent()}
    timeout = aiohttp.ClientTimeout(total=10)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, headers=headers) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return data