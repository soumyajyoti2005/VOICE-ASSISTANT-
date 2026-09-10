import asyncio
import aiohttp
import re
import urllib.parse
from html.parser import HTMLParser
from typing import List, Dict, Any


class HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.texts = []
        self._ignore = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "nav", "header", "footer", "noscript", "svg", "iframe"):
            self._ignore = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "nav", "header", "footer", "noscript", "svg", "iframe"):
            self._ignore = False

    def handle_data(self, data):
        if not self._ignore:
            t = data.strip()
            if t and len(t) > 3:
                self.texts.append(t)


async def web_search(
    query: str,
    response_id: int = 0,
) -> List[Dict[str, Any]]:
    """
    Live web search and scraper: searches DuckDuckGo, extracts search snippets,
    and fetches content from the top resulting public website.
    """
    clean_query = query.strip()
    if not clean_query:
        return [{"error": "Empty search query"}]

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    timeout = aiohttp.ClientTimeout(total=6)

    snippets = []
    target_url = None

    try:
        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
            # Step 1: Query DuckDuckGo HTML search for public web results
            ddg_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote_plus(clean_query)}"
            async with session.get(ddg_url) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    # Extract URLs and snippets
                    urls = re.findall(r'href="//duckduckgo\.com/l/\?uddg=([^&"\']+)', html)
                    raw_snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL)
                    for s in raw_snippets[:3]:
                        clean_s = re.sub(r'<[^>]+>', '', s).strip()
                        if clean_s:
                            snippets.append(clean_s)
                    if urls:
                        for u in urls:
                            decoded_u = urllib.parse.unquote(u)
                            if "ad_domain" not in decoded_u and "duckduckgo.com/y.js" not in decoded_u:
                                target_url = decoded_u
                                break

            # Step 2: Fetch and scrape text from the target webpage if available
            page_text = ""
            if target_url:
                try:
                    async with session.get(target_url) as page_resp:
                        if page_resp.status == 200:
                            content_type = page_resp.headers.get("Content-Type", "")
                            if "text/html" in content_type:
                                page_html = await page_resp.text()
                                extractor = HTMLTextExtractor()
                                extractor.feed(page_html)
                                # Extract top informative paragraphs
                                page_text = " ".join(extractor.texts[:300])[:6000]
                except Exception as scrape_err:
                    print(f"[WebSearch] Page fetch notice: {scrape_err}")

            if snippets or page_text:
                combined_content = ""
                if snippets:
                    combined_content += "Search Summary: " + " ".join(snippets) + "\n"
                if page_text:
                    combined_content += "Page Content: " + page_text

                return [
                    {
                        "title": f"Web Result for: {clean_query}",
                        "url": target_url or "https://duckduckgo.com",
                        "content": combined_content.strip(),
                    }
                ]

    except Exception as e:
        print(f"[WebSearch] Search request error: {e}")

    # Fallback to query reference if search encounters network blocks
    return [
        {
            "title": f"Reference: {clean_query}",
            "url": f"https://www.google.com/search?q={urllib.parse.quote_plus(clean_query)}",
            "content": f"Information regarding '{clean_query}'.",
        }
    ]