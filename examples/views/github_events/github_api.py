import ssl

import aiohttp
import certifi


GITHUB_EVENTS_URL = "https://api.github.com/events"

_timeout = aiohttp.ClientTimeout(total=10)
_ssl_context = ssl.create_default_context(cafile=certifi.where())


async def fetch_events(pages: int = 3) -> list[dict]:
    """Fetch recent public events from the GitHub Events API."""
    all_events: list[dict] = []
    connector = aiohttp.TCPConnector(ssl=_ssl_context)
    try:
        async with aiohttp.ClientSession(timeout=_timeout, connector=connector) as session:
            for page in range(1, pages + 1):
                async with session.get(
                    GITHUB_EVENTS_URL, params={"per_page": "100", "page": str(page)}
                ) as response:
                    if response.status != 200:
                        break
                    all_events.extend(await response.json())
    except Exception as e:
        print(f"Error fetching GitHub events: {e}")
    return all_events
