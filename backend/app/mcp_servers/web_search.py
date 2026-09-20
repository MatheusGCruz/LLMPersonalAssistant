import html as _html
import re
from urllib.parse import parse_qs, urlparse

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("web-search")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _clean_href(href: str) -> str:
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/l/"):
        query = parse_qs(urlparse(href).query)
        if "uddg" in query:
            return query["uddg"][0]
        return "https://duckduckgo.com" + href
    if href.startswith("/"):
        return "https://duckduckgo.com" + href
    return href


def _strip_tags(fragment: str) -> str:
    return _html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


def _search_html(query: str, max_results: int):
    response = httpx.get(
        "https://html.duckduckgo.com/html/",
        params={"q": query},
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    response.raise_for_status()
    blocks = re.split(r'<div[^>]*class="result"', response.text)
    results = []
    for block in blocks[1:]:
        href_match = re.search(r'class="result__a"[^>]*href="([^"]+)"', block)
        title_match = re.search(r'class="result__a"[^>]*>(.*?)</a>', block, re.S)
        snippet_match = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', block, re.S)
        if not href_match:
            continue
        href = _clean_href(href_match.group(1))
        title = _strip_tags(title_match.group(1)) if title_match else ""
        snippet = _strip_tags(snippet_match.group(1)) if snippet_match else ""
        results.append((href, title, snippet))
    return results[:max_results]


def _search_instant(query: str):
    response = httpx.get(
        "https://api.duckduckgo.com/",
        params={"q": query, "format": "json", "no_html": "1"},
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()
    hits = []
    if data.get("AbstractText"):
        hits.append((data.get("AbstractURL") or "", data.get("Heading") or "", data["AbstractText"]))
    for topic in data.get("RelatedTopics") or []:
        if isinstance(topic, dict) and topic.get("Text"):
            hits.append((topic.get("FirstURL") or "", topic.get("Text"), ""))
    return hits


@mcp.tool()
def web_search(query: str, max_results: int = 5) -> str:
    """Search the web and return up to max_results results with titles, URLs and snippets."""
    try:
        results = _search_html(query, max_results)
    except httpx.HTTPError:
        results = []
    if not results:
        try:
            results = _search_instant(query)[:max_results]
        except httpx.HTTPError:
            return f"web search unavailable for {query!r}"
    if not results:
        return f"no results for {query!r}"
    lines = []
    for index, (url, title, snippet) in enumerate(results, 1):
        lines.append(f"{index}. {title}\n   {url}\n   {snippet}".rstrip())
    return "\n\n".join(lines)


if __name__ == "__main__":
    mcp.run()