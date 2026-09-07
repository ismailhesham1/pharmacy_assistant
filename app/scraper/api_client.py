"""
Talks to two confirmed API endpoints:

  1. Bulk category-listing search:
     {API_BASE}/products/search?fields=FULL&query=:relevance:allCategories:{code}
         &currentPage=N&pageSize=...&lang=..&curr=..
     Returns many full product records per call, with real pagination. NEVER includes
     free-text description though, even with fields=FULL - confirmed by testing.

  2. Plain single-product endpoint (NOT /search or /multi/search):
     {API_BASE}/products/{code}?fields=FULL&lang=..&curr=..
     DOES include the full free-text description, under a custom 'aldawaaDescriptions'
     field (HTML), plus structured 'classifications' (product_form, product_function,
     features) and numeric stock level. This is what Pass 2 (enrichment) uses.

"""
import time

import requests

from config import (
    API_BASE, USER_AGENT, REQUEST_TIMEOUT_SECONDS, API_REQUEST_DELAY_SECONDS,
    CURRENCY, CATEGORY_PAGE_SIZE, MAX_RETRIES, RETRY_BACKOFF_BASE_SECONDS,
)

HEADERS = {"User-Agent": USER_AGENT}


def _get_with_retry(url: str, params: dict, extra_headers: dict | None = None) -> dict:
    """GET with exponential backoff on failure - important once we're running
    multiple concurrent workers, since occasional 429 (rate limited) or 5xx
    responses under load are expected and should be retried, not treated as a
    hard failure on the first attempt."""
    headers = {**HEADERS, **(extra_headers or {})}
    last_error = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
            if resp.status_code == 429 or resp.status_code >= 500:
                raise requests.HTTPError(f"status {resp.status_code}", response=resp)
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as e:
            last_error = e
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF_BASE_SECONDS * (2 ** attempt)
                time.sleep(wait)

    raise last_error


def fetch_category_products(category_code: str, lang: str):
    """
    Generator: yields raw product dicts for every product in the given category,
    across however many pages the API reports. Trusts the API's own pagination
    values rather than assuming CATEGORY_PAGE_SIZE was honored.
    """
    current_page = 0
    total_pages = 1  # updated after first response

    while current_page < total_pages:
        params = {
            "fields": "FULL",
            "query": f":relevance:allCategories:{category_code}",
            "currentPage": current_page,
            "pageSize": CATEGORY_PAGE_SIZE,
            "lang": lang,
            "curr": CURRENCY,
        }
        data = _get_with_retry(f"{API_BASE}/products/search", params)

        pagination = data.get("pagination", {})
        total_pages = pagination.get("totalPages", 1) #overwrites total_pages after first response

        for product in data.get("products", []):
            yield product

        current_page += 1
        time.sleep(API_REQUEST_DELAY_SECONDS)


def _extract_price_and_currency(raw: dict) -> tuple[float | None, str | None]:
    """
    Price lives in 'price' for normal products. Bundle/configurable products
    (observed: BP-prefixed product codes) have 'price' as null/missing and use
    'priceRange' instead - a min/max spread. We don't have a confirmed exact
    field name for the min value (couldn't verify live), so this tries a few
    reasonable variants defensively and falls back gracefully to None if none
    match. Verify against real repaired output and adjust if needed.
    """
    price = raw.get("price") or {}
    if price.get("value") is not None:
        return price.get("value"), price.get("currencyIso")

    price_range = raw.get("priceRange") or {}
    for key in ("minPrice", "min", "lowestPrice"):
        candidate = price_range.get(key)
        if candidate and candidate.get("value") is not None:
            return candidate.get("value"), candidate.get("currencyIso")

    return None, None


def _extract_brand_name(raw: dict) -> str | None:
    """Consistently None (not empty string) when brand is missing."""
    brand = raw.get("brand") or {}
    name = brand.get("name")
    return name if name else None


def normalize_api_product(raw: dict, lang: str, category_code: str) -> dict:
    """Converts the bulk-search API's raw product shape into our flat structured record."""
    stock = raw.get("stock") or {}
    price_value, currency = _extract_price_and_currency(raw) #unpack tuple into two variables

    image_urls = {img.get("key"): img.get("value") for img in raw.get("imageUrl", [])}

    return {
        "product_id": raw.get("code"),
        "lang": lang,
        "title": raw.get("name"),
        "brand": _extract_brand_name(raw),
        "price": price_value,
        "currency": currency,
        "in_stock": stock.get("stockLevelStatus") == "inStock" if stock.get("stockLevelStatus") else None,
        "stock_status_raw": stock.get("stockLevelStatus"),
        "category_code": category_code,
        "product_url": raw.get("url"),
        "image_url": image_urls.get(lang),
    }


def fetch_product_full(product_code: str, lang: str) -> dict:
    """The plain single-product endpoint - includes description + classifications."""
    params = {"fields": "FULL", "lang": lang, "curr": CURRENCY}
    # Explicit Accept header: without it, some clients get XML back from this
    # endpoint instead of JSON (observed when hitting it directly from a browser).
    return _get_with_retry(f"{API_BASE}/products/{product_code}", params,
                            extra_headers={"Accept": "application/json"})


def extract_description_text(product_full: dict) -> str | None:
    """
    aldawaaDescriptions is a list of {description: <HTML string>, position, videoPriority}.
    Concatenate by position and strip HTML down to plain text.
    """
    from bs4 import BeautifulSoup

    entries = product_full.get("aldawaaDescriptions") or []
    if not entries:
        return None
    entries = sorted(entries, key=lambda e: e.get("position", 0))
    html_parts = [e.get("description", "") for e in entries if e.get("description")]
    if not html_parts:
        return None
    combined_html = "\n".join(html_parts)
    text = BeautifulSoup(combined_html, "lxml").get_text("\n", strip=True)
    return text or None


def extract_classifications(product_full: dict) -> dict:
    """Pulls the structured feature fields (product_form, product_function, features,
    etc.) out of 'classifications' - useful metadata for filtering/recommendation."""
    result = {}
    for classification in product_full.get("classifications") or []:
        for feature in classification.get("features") or []:
            code = feature.get("code", "")
            key = code.rsplit(".", 1)[-1] if "." in code else code  # last segment, e.g. "product_form"
            values = [v.get("value") for v in feature.get("featureValues") or [] if v.get("value")]
            if values:
                result[key] = values if len(values) > 1 else values[0]
    return result


def normalize_full_product(product_full: dict, lang: str) -> dict:
    """Full record from the single-product endpoint - structured fields + description."""
    stock = product_full.get("stock") or {}
    price_value, currency = _extract_price_and_currency(product_full)
    categories = product_full.get("categories") or []
    if isinstance(categories, dict):  # API sometimes returns a single dict instead of a list
        categories = [categories]

    return {
        "product_id": product_full.get("code"),
        "lang": lang,
        "title": product_full.get("name"),
        "brand": _extract_brand_name(product_full),
        "price": price_value,
        "currency": currency,
        "in_stock": stock.get("stockLevelStatus") == "inStock" if stock.get("stockLevelStatus") else None,
        "stock_status_raw": stock.get("stockLevelStatus"),
        "stock_level": stock.get("stockLevel"),
        "category_path": [c.get("name") for c in categories if c.get("name")],
        "product_url": product_full.get("url"),
        "description": extract_description_text(product_full),
        "classifications": extract_classifications(product_full),
    }


if __name__ == "__main__":
    # Sanity check against the confirmed First Aid category (code 6005).
    count = 0
    for raw in fetch_category_products("6005", "en"):
        normalized = normalize_api_product(raw, "en", "6005")
        if count < 3:
            print(normalized)
        count += 1
        if count >= 5:  # don't pull the whole category during a quick sanity check
            break
    print(f"\nPulled {count} products (stopped early for this sanity check)")
