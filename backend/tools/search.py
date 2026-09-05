import asyncio
from typing import List, Dict, Any


async def web_search(
    query: str,
    response_id: int = 0,
) -> List[Dict[str, Any]]:
    await asyncio.sleep(2)

    return [
        {
            "title": f"Search result for: {query}",
            "snippet": f"This is a mock search result for '{query}'. In production, this would call a real search API.",
            "url": "https://example.com/result1",
        },
        {
            "title": f"More about {query}",
            "snippet": f"Additional information related to '{query}' would appear here.",
            "url": "https://example.com/result2",
        },
    ]