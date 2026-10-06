"""Provider identifiers stay strings, including ISBNs and large Kakuyomu IDs."""
import re

from .contracts import AdapterError


def normalize_isbn(value: str) -> str:
    value = re.sub(r"[^0-9Xx]", "", value)
    if len(value) == 10:
        if any(ch.upper() == "X" for ch in value[:-1]):
            raise AdapterError("Invalid ISBN checksum")
        if sum((10 - i) * (10 if ch.upper() == "X" else int(ch)) for i, ch in enumerate(value)) % 11:
            raise AdapterError("Invalid ISBN checksum")
        prefix = "978" + value[:-1]
        value = prefix + str((10 - sum(int(ch) * (1 if i % 2 == 0 else 3) for i, ch in enumerate(prefix)) % 10) % 10)
    if len(value) != 13 or not value.isdigit() or not value.startswith(("978", "979")) or sum(int(ch) * (1 if i % 2 == 0 else 3) for i, ch in enumerate(value)) % 10:
        raise AdapterError("Invalid ISBN checksum")
    return value


def shogakukan_product_id(isbn: str) -> str:
    value = normalize_isbn(isbn)
    if not value.startswith("9784"):
        raise AdapterError("A Japanese Shogakukan ISBN is required")
    return value[4:12]
