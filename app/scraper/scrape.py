import hashlib
import json
import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from config import (
    USER_AGENT,
    API_REQUEST_DELAY_SECONDS,
    HTML_REQUEST_DELAY_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
    RAW_HTML_DIR,
    PRODUCTS_STRUCTURED_PATH,
    PRODUCTS_FULL_PATH,
    FAILED_URLS_PATH,
    MAX_WORKERS,
    CATEGORY_WORKERS,
    LANGS,
)
from sitemap import get_robot_parser, get_category_codes, get_content_urls
from api_client import fetch_category_products, normalize_api_product, fetch_product_full, normalize_full_product
from parser import parse_content_page

HEADERS = {"User-Agent": USER_AGENT}

#2 fns only used for policy pages, not products
def _cache_path(url: str) -> str:
    h = hashlib.sha256(url.encode()).hexdigest()[:16]
    return os.path.join(RAW_HTML_DIR, f"{h}.html")


def fetch_html(url: str) -> str:
    path = _cache_path(url)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
    resp.raise_for_status()
    html = resp.text

    os.makedirs(RAW_HTML_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

    time.sleep(HTML_REQUEST_DELAY_SECONDS)
    return html




def load_structured_records() -> list[dict]:
    records = []
    with open(PRODUCTS_STRUCTURED_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _load_completed_keys(path: str) -> set[tuple]:
    """Reads an existing output file (if any) and returns the (product_id, lang)
    keys already present, so a resumed run can skip them instead of re-fetching."""
    keys = set()
    if not os.path.exists(path):
        return keys
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                keys.add((record.get("product_id"), record.get("lang")))
            except json.JSONDecodeError:
                continue  # tolerate a truncated last line from a killed process
    return keys


def _fetch_category_pair(code: str, lang: str) -> tuple[str, str, list[dict], str | None]:
    """Worker function for Pass 1: fetch + normalize every product in one
    (category_code, lang) pair. Returns (code, lang, records, error)."""
    try:
        records = [normalize_api_product(raw, lang, code) for raw in fetch_category_products(code, lang)]
        return code, lang, records, None
    except Exception as e:
        return code, lang, [], str(e)


def run_bulk_pass(rp) -> list[dict]:
    """Pass 1: structured data for the full catalog via the bulk category API.
    Concurrent across (category, lang) pairs - with thousands of categories x 2
    languages, this needs the same concurrency treatment as Pass 2, not just a
    lower delay."""
    codes = get_category_codes(rp)
    print(f"\n{len(codes)} category codes found\n")

    os.makedirs(os.path.dirname(PRODUCTS_STRUCTURED_PATH), exist_ok=True)
    all_records: list[dict] = []
    seen_keys: set[tuple] = set()  # (product_id, lang) - products can appear in multiple categories
    write_lock = threading.Lock()
    completed = 0
    completed_lock = threading.Lock()

    tasks = [(code, lang) for code in codes for lang in LANGS]
    total_tasks = len(tasks)

    with open(PRODUCTS_STRUCTURED_PATH, "w", encoding="utf-8") as out_f, \
         ThreadPoolExecutor(max_workers=CATEGORY_WORKERS) as executor:

        futures = [executor.submit(_fetch_category_pair, code, lang) for code, lang in tasks]

        for future in as_completed(futures):
            code, lang, records, error = future.result()
            if error:
                print(f"  FAILED category {code} ({lang}): {error}")
            else:
                with write_lock:
                    for record in records:
                        key = (record["product_id"], record["lang"])
                        if key in seen_keys:
                            continue  # already pulled from another category
                        seen_keys.add(key)
                        all_records.append(record)
                        out_f.write(json.dumps(record, ensure_ascii=False) + "\n")

            with completed_lock:
                completed += 1
                if completed % 50 == 0:
                    print(f"  ...{completed}/{total_tasks} category/lang pairs processed, "
                          f"{len(all_records)} unique products so far")

    print(f"\nPass 1 done: {len(all_records)} unique products -> {PRODUCTS_STRUCTURED_PATH}")
    return all_records


def _enrich_one(record: dict) -> dict | None:
    """Worker function: fetch + normalize one product. Each thread paces its OWN
    requests with API_REQUEST_DELAY_SECONDS - with MAX_WORKERS threads each doing this,
    the effective combined request rate is roughly MAX_WORKERS / API_REQUEST_DELAY_SECONDS
    per second, not unlimited."""
    product_id = record["product_id"]
    lang = record["lang"]
    try:
        raw_full = fetch_product_full(product_id, lang)
        merged = normalize_full_product(raw_full, lang)
        time.sleep(API_REQUEST_DELAY_SECONDS)
        return merged
    except Exception as e:
        print(f"  FAILED ({e}): product {product_id} ({lang})")
        time.sleep(API_REQUEST_DELAY_SECONDS)
        return None


def run_enrichment_pass(structured_records: list[dict]) -> None:
    """
    Pass 2: fetch the full single-product record (structured fields + description)
    for EVERY product from Pass 1, both languages, run concurrently.

    Resumable: if PRODUCTS_FULL_PATH already has some products in it (from a
    previous run that was interrupted or partially failed), those are skipped and
    the file is appended to rather than overwritten - so re-running after a failure
    only redoes the remaining work, not everything.
    """
    os.makedirs(os.path.dirname(PRODUCTS_FULL_PATH), exist_ok=True)

    already_done = _load_completed_keys(PRODUCTS_FULL_PATH)
    remaining = [r for r in structured_records
                 if (r["product_id"], r["lang"]) not in already_done]

    total = len(structured_records)
    if already_done:
        print(f"\nFound {len(already_done)} already-enriched products from a previous run - resuming.")
    print(f"\nPass 2: enriching {len(remaining)}/{total} remaining products with {MAX_WORKERS} workers\n")

    if not remaining:
        print("Nothing left to do.")
        return

    write_lock = threading.Lock()
    failed_lock = threading.Lock()
    failed: list[str] = []
    completed = 0
    completed_lock = threading.Lock()

    # append mode: preserves whatever's already in the file from a previous run
    with open(PRODUCTS_FULL_PATH, "a", encoding="utf-8") as out_f, \
         ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:

        futures = {executor.submit(_enrich_one, r): r for r in remaining}

        for future in as_completed(futures):
            record = futures[future]
            result = future.result()

            if result is not None:
                with write_lock:
                    out_f.write(json.dumps(result, ensure_ascii=False) + "\n")
            else:
                with failed_lock:
                    failed.append(f"{record['product_id']}:{record['lang']}")

            with completed_lock:
                completed += 1
                if completed % 100 == 0:
                    print(f"  ...{completed}/{len(remaining)} enriched this run")

    if failed:
        with open(FAILED_URLS_PATH, "w", encoding="utf-8") as f:
            f.write("\n".join(failed))
        print(f"\n{len(failed)} products failed during enrichment - see {FAILED_URLS_PATH}"
              f" (re-run scrape.py to retry just these - already-completed ones will be skipped)")

    print(f"\nPass 2 done -> {PRODUCTS_FULL_PATH}")


def run_content_pages(rp) -> None:
    """Policy/FAQ/CMS pages - small in number, fetched directly as HTML, sequential."""
    urls = get_content_urls(rp)
    print(f"\n{len(urls)} content/policy URLs to process\n")

    content_out_path = os.path.join(os.path.dirname(PRODUCTS_FULL_PATH), "content_pages.jsonl")
    with open(content_out_path, "w", encoding="utf-8") as out_f:
        for url in urls:
            lang = "ar" if "/ar/" in url else "en"
            try:
                html = fetch_html(url)
                record = parse_content_page(html, url, lang)
                out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
            except Exception as e:
                print(f"  FAILED ({e}): {url}")

    print(f"Content pages done -> {content_out_path}")


def run():
    rp = get_robot_parser()

    # If Pass 1 already completed (file exists and has content), don't redo it -
    # this is exactly the "Pass 1 succeeded, Pass 2 failed" case: just re-run
    # scrape.py and it'll skip straight to (resuming) Pass 2.
    if os.path.exists(PRODUCTS_STRUCTURED_PATH) and os.path.getsize(PRODUCTS_STRUCTURED_PATH) > 0:
        print(f"Found existing {PRODUCTS_STRUCTURED_PATH} - skipping Pass 1.")
        print("(Delete this file first if you want to force a fresh Pass 1 re-scrape.)\n")
        structured_records = load_structured_records()
    else:
        structured_records = run_bulk_pass(rp)

    run_enrichment_pass(structured_records)
    run_content_pages(rp)

    print("\nAll done.")


if __name__ == "__main__":
    run()
