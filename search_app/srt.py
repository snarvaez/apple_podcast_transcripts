"""Convert subtitle files into plain transcript text."""

from __future__ import annotations

import re

_INDEX = re.compile(r"^\d+$")
_TIMESTAMP = re.compile(
    r"^\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,.]\d{3}"
)
_TAG = re.compile(r"<[^>]+>")


def srt_to_text(srt: str) -> str:
    srt = (srt or "").lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    parts: list[str] = []
    for block in re.split(r"\n\s*\n", srt.strip()):
        lines = []
        for line in block.splitlines():
            stripped = line.strip()
            if not stripped or _INDEX.match(stripped) or _TIMESTAMP.match(stripped):
                continue
            lines.append(_TAG.sub("", stripped))
        if lines:
            parts.append(" ".join(lines))
    text = " ".join(parts)
    return re.sub(r"\s+", " ", text).strip()
