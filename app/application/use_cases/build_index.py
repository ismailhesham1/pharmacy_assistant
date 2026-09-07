from domain.entities import ProductChunk, PolicyChunk, IndexBuildResult

MAX_POLICY_CHUNK_CHARS = 1200


def merge_product_records(structured: list[dict], full: list[dict]) -> list[dict]:
    image_urls = {(r.get("product_id"), r.get("lang")): r.get("image_url") for r in structured}
    merged = []
    for record in full:
        key = (record.get("product_id"), record.get("lang"))
        merged.append({**record, "image_url": image_urls.get(key)})
    return merged


def build_embed_text(record: dict) -> tuple[str, bool]:
    title = record.get("title") or ""
    description = record.get("description")

    if description:
        classifications = record.get("classifications") or {}
        class_values = " ".join(
            " ".join(v) if isinstance(v, list) else str(v)
            for v in classifications.values()
        )
        text = f"{title}. {description}"
        if class_values:
            text += f" {class_values}"
        return text.strip(), False
#fallback to title + brand + category path if description is missing
    category_path = record.get("category_path") or []
    brand = record.get("brand")
    parts = [title]
    if brand:
        parts.append(f"Brand: {brand}")
    if category_path:
        parts.append(f"Category: {' > '.join(category_path)}")
    return ". ".join(p for p in parts if p).strip(), True


def to_product_chunk(record: dict) -> ProductChunk:
    embed_text, used_fallback = build_embed_text(record)
    return ProductChunk(
        product_id=record.get("product_id"),
        lang=record.get("lang"),
        embed_text=embed_text,
        title=record.get("title"),
        price=record.get("price"),
        currency=record.get("currency"),
        in_stock=record.get("in_stock"),
        brand=record.get("brand"),
        category_path=record.get("category_path") or [],
        product_url=record.get("product_url"),
        image_url=record.get("image_url"),
        used_fallback_text=used_fallback,
    )


def split_policy_text(text: str, max_chunk_chars: int = MAX_POLICY_CHUNK_CHARS) -> list[tuple[str, str]]:
    if not text:
        return []

    lines = [l.strip() for l in text.split("\n") if l.strip()]

    def is_heading(line: str) -> bool:
        # A real section heading is short AND has more than one word - a lone
        # word (common artifact in some of the scraped Arabic text, which has
        # portions formatted one-word-per-line) should never count as a heading,
        # or the whole section fragments into near-meaningless one-word chunks.
        return len(line) < 80 and len(line.split()) >= 2 and not line.endswith((".", "،", "؟", "!"))

    chunks: list[tuple[str, str]] = []
    current_title = "General"
    current_lines: list[str] = []

    if lines and is_heading(lines[0]):
        current_title = lines[0]
        lines = lines[1:]

    def flush():
        if current_lines:
            chunks.append((current_title, "\n".join(current_lines).strip()))

    for line in lines:
        current_length = sum(len(l) for l in current_lines)
        if is_heading(line) and current_lines:
            flush()
            current_title = line
            current_lines = []
        elif current_length > max_chunk_chars:
            flush()
            current_lines = [line]
        else:
            current_lines.append(line)

    flush()
    return [(title, text) for title, text in chunks if text]


def content_page_to_policy_chunks(page: dict) -> list[PolicyChunk]:
    text = page.get("text") or ""
    if not text.strip():
        return []

    sections = split_policy_text(text)
    return [
        PolicyChunk(
            source_url=page.get("url"),
            lang=page.get("lang"),
            section_title=section_title,
            text=section_text,
        )
        for section_title, section_text in sections
    ]


def build_index(structured: list[dict], full: list[dict], content_pages: list[dict]) -> IndexBuildResult:
    merged_products = merge_product_records(structured, full)

    result = IndexBuildResult()
    for record in merged_products:
        chunk = to_product_chunk(record)
        result.product_chunks.append(chunk)
        if chunk.used_fallback_text:
            result.products_missing_description += 1  #counter

    for page in content_pages:
        result.policy_chunks.extend(content_page_to_policy_chunks(page))

    return result