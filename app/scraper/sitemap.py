import re
import time
from urllib.robotparser import RobotFileParser #reads robot.txt
from xml.etree import ElementTree as ET #xml parser
import requests

from config import (
    SITEMAP_INDEX_URL,
    ROBOTS_URL,
    USER_AGENT,
    REQUEST_TIMEOUT_SECONDS,
    API_REQUEST_DELAY_SECONDS,
    SITEMAP_TYPES_TO_SCRAPE,
    LANGS,
)

HEADERS = {"User-Agent": USER_AGENT}
SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def get_robot_parser() -> RobotFileParser:
    """
    Deliberately NOT using rp.read() here. RobotFileParser.read() fetches robots.txt
    using urllib's default User-Agent, and sites behind a WAF (Cloudflare/Akamai etc.)
    frequently return 403 for generic/default user-agents specifically on robots.txt -
    which makes robotparser silently set disallow_all=True, blocking every URL.
    Fetching it ourselves with our real headers avoids that.
    """
    resp = requests.get(ROBOTS_URL, headers=HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
    resp.raise_for_status()

    rp = RobotFileParser()
    rp.set_url(ROBOTS_URL)
    rp.parse(resp.text.splitlines()) # gets handed downloaded text not file
    return rp


def _fetch_xml(url: str) -> ET.Element:
    resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
    resp.raise_for_status()
    return ET.fromstring(resp.content)


def get_sub_sitemap_urls() -> list[str]:
    """Fetch the sitemap index and return sub-sitemap URLs matching what we care about."""
    root = _fetch_xml(SITEMAP_INDEX_URL)
    all_sub_sitemaps = [el.text for el in root.findall(".//sm:loc", SITEMAP_NS)]

    wanted = []
    for url in all_sub_sitemaps:
        filename = url.rsplit("/", 1)[-1]  # e.g. "Category-en-SAR.xml"
        sitemap_type = filename.split("-")[0]  # "Category"
        lang = filename.split("-")[1] if "-" in filename else None  # "en"
        if sitemap_type in SITEMAP_TYPES_TO_SCRAPE and lang in LANGS:
            wanted.append(url)
    return wanted


def get_page_urls_from_sitemap(sitemap_url: str) -> list[str]:
    root = _fetch_xml(sitemap_url)
    return [el.text for el in root.findall(".//sm:loc", SITEMAP_NS)]


def get_category_codes(rp: RobotFileParser) -> list[str]:
    """
    Fetches the Category sitemap(s) and extracts category codes from URLs like
    '.../home-health-care/first-aid/c/6005' -> '6005'.
    Codes are language-independent (same catalog structure under /en/ and /ar/),
    so we dedupe across both sitemap languages into one list of codes.
    """
    sub_sitemaps = get_sub_sitemap_urls()
    category_sitemaps = [u for u in sub_sitemaps if "Category-" in u]

    codes: set[str] = set()
    for sm_url in category_sitemaps:
        print(f"Fetching category sitemap: {sm_url}")
        urls = get_page_urls_from_sitemap(sm_url)
        allowed = [u for u in urls if rp.can_fetch(USER_AGENT, u)]
        for u in allowed:
            m = re.search(r"/c/(\d+)$", u)
            if m:
                codes.add(m.group(1))
        time.sleep(API_REQUEST_DELAY_SECONDS)

    return sorted(codes)


def get_content_urls(rp: RobotFileParser) -> list[str]:
    """Policy/FAQ/CMS pages from the Content sitemap(s)."""
    sub_sitemaps = get_sub_sitemap_urls()
    content_sitemaps = [u for u in sub_sitemaps if "Content-" in u]

    all_urls: list[str] = []
    for sm_url in content_sitemaps:
        print(f"Fetching content sitemap: {sm_url}")
        urls = get_page_urls_from_sitemap(sm_url)

        # Their sitemap has a known bug: at least one entry is a literal unescaped
        # template placeholder (e.g. ".../en${siteMapUrl.loc}") instead of a real
        # URL - filter these out before they get fetched as if real (confirmed:
        # fetching one just returns their generic 404 page).
        urls = [u for u in urls if "${" not in u]

        allowed = [u for u in urls if rp.can_fetch(USER_AGENT, u)]
        skipped = len(urls) - len(allowed)
        if skipped:
            print(f"  skipped {skipped} URL(s) disallowed by robots.txt")
        all_urls.extend(allowed)
        time.sleep(API_REQUEST_DELAY_SECONDS)

    seen = set()
    deduped = []
    for u in all_urls:
        if u not in seen:
            seen.add(u)
            deduped.append(u)
    return deduped


if __name__ == "__main__":
    rp = get_robot_parser()
    codes = get_category_codes(rp)
    print(f"\n{len(codes)} category codes found")
    print("Sample:", codes[:10])

    content_urls = get_content_urls(rp)
    print(f"\n{len(content_urls)} content/policy URLs found")
    print("Sample:", content_urls[:5])
