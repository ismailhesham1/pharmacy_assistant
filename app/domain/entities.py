from dataclasses import dataclass, field


@dataclass
class ProductChunk:
    """One product, one language - the unit that gets embedded + indexed."""
    product_id: str
    lang: str                      # "en" or "ar"
    embed_text: str                # what gets turned into a vector (title + description/fallback)
    title: str
    price: float | None
    currency: str | None
    in_stock: bool | None
    brand: str | None
    category_path: list[str]
    product_url: str | None
    image_url: str | None
    used_fallback_text: bool = False   # True if description was missing and we used title+category instead


@dataclass
class PolicyChunk:
    """One section of a policy/content page - split by header, not embedded as one giant blob."""
    source_url: str
    lang: str
    section_title: str
    text: str


@dataclass
class IndexBuildResult:
    """Summary returned after building the index - for logging/sanity-checking, not stored anywhere."""
    product_chunks: list[ProductChunk] = field(default_factory=list)
    policy_chunks: list[PolicyChunk] = field(default_factory=list)
    products_missing_description: int = 0