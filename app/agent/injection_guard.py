import re

_PATTERNS = [
    r"ignore\s+(all\s+)?(the\s+)?(previous|prior|above)\s+instructions",
    r"disregard\s+(all\s+)?(the\s+)?(previous|prior|above)\s+instructions",
    r"ignore\s+(all\s+)?(the\s+)?(previous|prior|above)\s+rules",
    r"forget\s+(that\s+)?(you\s+are|your\s+(role|instructions|rules))",
    r"reveal\s+(your\s+|the\s+)?system\s+prompt",
    r"show\s+(me\s+)?(your\s+|the\s+)?system\s+prompt",
    r"repeat\s+(your\s+|the\s+)?system\s+prompt",
    r"what\s+(is|are)\s+your\s+(system\s+prompt|instructions|rules)",
    r"pretend\s+(that\s+)?you\s+are\s+(a\s+different|not)",
    r"act\s+as\s+(a\s+)?(different|unrestricted|jailbroken)",
    r"you\s+are\s+now\s+(a|an)\s+\w+",
    r"(developer|admin|debug)\s+mode",
    r"as\s+the\s+(developer|admin|system)\b",
    r"do\s+not\s+(add|include|show)\s+(the\s+)?disclaimer",
    r"without\s+(the\s+)?disclaimer",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in _PATTERNS]


def check_for_injection(text: str) -> bool:
    """Returns True if the text matches a known injection pattern. Detection
    only - the actual defense is the system prompt, this is visibility only."""
    return any(pattern.search(text) for pattern in _COMPILED)