import json
import os


def load_jsonl(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def load_scraper_output(scraper_data_dir: str) -> tuple[list[dict], list[dict], list[dict]]:
    """
    Returns (products_structured, products_full, content_pages) as raw dicts,
    read from the scraper's data/ directory (e.g. app/scraper/data/).
    """
    structured = load_jsonl(os.path.join(scraper_data_dir, "products_structured.jsonl"))
    full = load_jsonl(os.path.join(scraper_data_dir, "products_full.jsonl"))
    content = load_jsonl(os.path.join(scraper_data_dir, "content_pages.jsonl"))
    return structured, full, content