import re
import json
from bs4 import BeautifulSoup

#not used 
def parse_product(html: str, url: str, lang: str) -> dict:
    soup = BeautifulSoup(html, "lxml")

    product_id = _extract_product_id(url)
    product_ld = _extract_json_ld(soup, "ald-ld-json-product-product")
    breadcrumb_ld = _extract_json_ld(soup, "ald-ld-json-breadcrumb-breadcrumb")

    title = product_ld.get("name") if product_ld else None
    brand = (product_ld.get("brand") or {}).get("name") if product_ld else None
    image_url = product_ld.get("image") if product_ld else None

    offer = (product_ld.get("offers") or {}) if product_ld else {}
    price = offer.get("price")
    currency = offer.get("priceCurrency")
    in_stock = _parse_availability(offer.get("availability"))

    category_path = _extract_breadcrumb_names(breadcrumb_ld)

    # Free-text description isn't in the JSON-LD (confirmed empty on real products) -
    # still needs the HTML section.
    description = _extract_description(soup)

    return {
        "product_id": product_id,
        "url": url,
        "lang": lang,
        "title": title,
        "brand": brand,
        "price": price,
        "currency": currency,
        "in_stock": in_stock,
        "image_url": image_url,
        "category_path": category_path,   # list of breadcrumb strings, e.g. ["Home", "Growth Formula"]
        "description": description,        # dict: {"overview": str, "bullets": [str, ...]}
    }


def parse_content_page(html: str, url: str, lang: str) -> dict:
    """For policy/FAQ/CMS pages (the 'Content' sitemap). Structure is likely different
    from product pages - VERIFY against a real fetched page before relying on this."""
    soup = BeautifulSoup(html, "lxml")

    title_el = soup.find("h1")
    title = title_el.get_text(strip=True) if title_el else None

    # Grab the main text content - very rough, strips nav/header/footer chrome.
    for tag in soup(["nav", "header", "footer", "script", "style"]):
        tag.decompose()

    main = soup.find("main") or soup.body
    text = main.get_text("\n", strip=True) if main else ""

    return {
        "url": url,
        "lang": lang,
        "title": title,
        "text": text,
    }


def _extract_product_id(url: str) -> str | None:
    match = re.search(r"/p/(\d+)/", url)
    return match.group(1) if match else None


def _extract_json_ld(soup: BeautifulSoup, script_id: str) -> dict | None:
    tag = soup.find("script", id=script_id)
    if not tag or not tag.string:
        return None
    try:
        return json.loads(tag.string)
    except json.JSONDecodeError:
        return None


def _parse_availability(availability_url: str | None) -> bool | None:
    """schema.org availability is a URL like 'https://schema.org/InStock' or
    'https://schema.org/OutOfStock' - just check which one it ends with."""
    if not availability_url:
        return None
    if availability_url.endswith("InStock"):
        return True
    if availability_url.endswith("OutOfStock"):
        return False
    return None  # other schema.org values exist (LimitedAvailability, etc.) - treat as unknown


def _extract_breadcrumb_names(breadcrumb_ld: dict | None) -> list[str]:
    if not breadcrumb_ld:
        return []
    items = breadcrumb_ld.get("itemListElement", [])
    # itemListElement is already ordered by "position" - sort defensively anyway
    items = sorted(items, key=lambda x: x.get("position", 0))
    return [item.get("name") for item in items if item.get("name")]


def _extract_description(soup: BeautifulSoup) -> dict:
    container = soup.select_one(".aldawaa-product-details")
    if not container:
        return {"overview": None, "bullets": []}

    # Strip the "Show more" toggle span itself so it doesn't pollute the text
    for toggle in container.select(".show-more"):
        toggle.decompose()

    bullets = [li.get_text(strip=True) for li in container.find_all("li")]

    paragraphs = [
        p.get_text(strip=True)
        for p in container.find_all(["p", "h2", "h3"])
        if p.get_text(strip=True)
    ]
    overview = " ".join(paragraphs) if paragraphs else None

    return {"overview": overview, "bullets": bullets}


if __name__ == "__main__":
    # Sanity check using the ACTUAL JSON-LD shape confirmed from real page source,
    # plus the confirmed .aldawaa-product-details description block.
    mock_html = """
    <html><body>
    <script type="application/ld+json" id="ald-ld-json-product-product">
    {"@context":"https://schema.org","@type":"Product",
     "name":"Pediasure, Complete 1+ Vanilla 400 Gm",
     "image":"https://stgprevapi.al-dawaa.com/medias/example.webp",
     "description":"",
     "brand":{"@type":"Brand","name":"Pediasure"},
     "offers":{"@type":"Offer","priceCurrency":"SAR","price":56.61,
               "availability":"https://schema.org/InStock"}}
    </script>
    <script type="application/ld+json" id="ald-ld-json-breadcrumb-breadcrumb">
    {"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[
        {"@type":"ListItem","position":1,"name":"Home","item":"https://www.al-dawaa.com/en/"},
        {"@type":"ListItem","position":2,"name":"Growth Formula","item":"https://www.al-dawaa.com/en/mum-and-baby/baby-milk/growth-formula/c/101107"}
    ]}
    </script>
    <div class="aldawaa-product-details-heading">Product Description</div>
    <div class="aldawaa-product-details">
        <h3>Product Overview - Pediasure Complete 1+ Vanilla</h3>
        <p>Supports children's growth and development.</p>
        <ul>
            <li>Complete balanced nutrition</li>
            <li>Suitable for picky eaters</li>
        </ul>
        <span class="show-more">Show more</span>
    </div>
    </body></html>
    """
    result = parse_product(mock_html, "https://www.al-dawaa.com/en/p/300699/pediasure-complete-1-vanilla-400-gm", "en")
    print(json.dumps(result, indent=2, ensure_ascii=False))
