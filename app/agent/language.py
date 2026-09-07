import re

ARABIC_PATTERN = re.compile(r"[\u0600-\u06FF\u0750-\u077F]")


def detect_language(text: str) -> str:
    """Returns 'ar' if the text contains Arabic script, else 'en'."""
    if ARABIC_PATTERN.search(text):
        return "ar"
    return "en"