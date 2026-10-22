"""Read a secret that may have been written on Windows.

PowerShell 5 writes UTF-16 with a BOM for `>` and UTF-8 with a BOM for `-Encoding UTF8`; editors add CRLF. A BOM that
stays inside the token makes the service reject the very token a person copies into n8n, with no visible difference.
"""
from __future__ import annotations

import re
from pathlib import Path


def decode_secret(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = data.decode("utf-16")
    else:
        text = data.decode("utf-8-sig")
    return text.strip()


def read_secret(path: str | Path, min_length: int = 24) -> str:
    """Return the cleaned secret or raise ValueError with a message that never contains the secret itself."""
    try:
        text = decode_secret(Path(path).read_bytes())
    except UnicodeDecodeError:
        raise ValueError(f"{path}: not valid UTF-8 or UTF-16 text; recreate it as plain ASCII")
    if not re.fullmatch(r"[\x21-\x7e]+", text or " "):
        raise ValueError(f"{path}: contains spaces, line breaks inside the value, or non-ASCII characters; recreate it as plain ASCII")
    if len(text) < min_length:
        raise ValueError(f"{path}: must be at least {min_length} characters")
    return text
