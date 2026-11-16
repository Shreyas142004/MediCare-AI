import re
from typing import List

def clean_ocr_text(raw_text: str) -> str:
    """Removes non-printable characters and normalizes whitespace."""
    if not raw_text:
        return ""
    # Replace newlines and tabs with spaces
    text = re.sub(r'[\r\n\t]+', ' ', raw_text)
    # Remove unwanted special characters, keeping alphanumeric, periods, slashes, hyphens, percent
    text = re.sub(r'[^a-zA-Z0-9\s\.\,\-\/\%\(\)]', ' ', text)
    # Consolidate multiple spaces
    return " ".join(text.split())

def normalize_for_matching(text: str) -> str:
    """Produces a clean alphanumeric lowercase string for string comparison."""
    if not text:
        return ""
    cleaned = re.sub(r'[^a-zA-Z0-9\s]', ' ', str(text)).lower()
    return " ".join(cleaned.split())

def tokenize_words(text: str) -> List[str]:
    """Tokenizes text into distinct alphabetic and numeric words."""
    if not text:
        return []
    return [w for w in re.split(r'[^a-zA-Z0-9]+', text.strip()) if len(w) > 1]

