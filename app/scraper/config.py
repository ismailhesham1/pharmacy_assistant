BASE_URL = "https://www.al-dawaa.com"
API_BASE = "https://stgprevapi.al-dawaa.com/occ/v2/aldawaa"
SITEMAP_INDEX_URL = f"{BASE_URL}/sitemap.xml"
ROBOTS_URL = f"{BASE_URL}/robots.txt"

USER_AGENT = "PharmacyAssistantScraper/1.0 (student project; contact: you@example.com)"

# Two delay settings, not one - these requests are not equivalent:
#   API_REQUEST_DELAY_SECONDS: lightweight JSON API calls (category search, product
#       detail). Small payload, no rendering - their own frontend already fires dozens
#       of these in parallel per page load, so 0.5s per worker is still clearly polite.
#   HTML_REQUEST_DELAY_SECONDS: full page fetches (content/policy pages only, now).
#       Heavier request, and there are few of these, so no need to push this one down.
API_REQUEST_DELAY_SECONDS = 0.5
HTML_REQUEST_DELAY_SECONDS = 1.5
REQUEST_TIMEOUT_SECONDS = 15

CURRENCY = "SAR"

# Bulk category-listing pass (Pass 1): confirmed via DevTools that
# products/search?query=:relevance:allCategories:{code} returns many full product
# records per call, with real pagination.
CATEGORY_PAGE_SIZE = 100  # code trusts the API's own returned pagination values
                           # regardless, so this is safe even if silently capped lower.
CATEGORY_WORKERS = 8       # concurrent threads for Pass 1 (4,100 categories x 2 langs
                            # is a lot of requests even though each one is small/fast -
                            # needs concurrency same as Pass 2, not just a lower delay).

# Enrichment pass (Pass 2): the plain single-product endpoint
# (products/{code}?fields=FULL) - confirmed to include full description +
# classifications + stock level, all in one call. No cap - full catalog, both
# languages - made feasible via concurrency (MAX_WORKERS below), not a smaller scope.
MAX_WORKERS = 8            # concurrent threads for Pass 2. Moderate/safer level - see
                            # the tradeoff discussion: higher = faster but more likely
                            # to trip rate-limiting on their end.
MAX_RETRIES = 3             # per-request retry count on failure (429/5xx/timeout)
RETRY_BACKOFF_BASE_SECONDS = 2  # exponential backoff: 2s, 4s, 8s between retries

# Output locations
RAW_HTML_DIR = "data/raw_html"
PRODUCTS_STRUCTURED_PATH = "data/products_structured.jsonl"  # Pass 1 output
PRODUCTS_FULL_PATH = "data/products_full.jsonl"                # Pass 2 output
FAILED_URLS_PATH = "data/failed_products.txt"

LANGS = ["en", "ar"]

# Sitemap files we still need directly (policy/content pages aren't in the bulk
# product API, and category codes are discovered from the Category sitemap).
SITEMAP_TYPES_TO_SCRAPE = ["Category", "Content"]
