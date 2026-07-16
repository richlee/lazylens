from __future__ import annotations

import re
from pathlib import Path


TEXT_EXTENSIONS = {
    ".csv",
    ".html",
    ".json",
    ".md",
    ".rst",
    ".text",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}


def compact_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def title_from_text(path: Path, text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            if title:
                return title
    return path.stem.replace("_", " ").replace("-", " ").strip() or path.name


def useful_snippet(text: str, *, limit: int = 500) -> str:
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("#", "---", "```")):
            continue
        lines.append(stripped)
        if len(" ".join(lines)) >= limit:
            break
    return compact_text(" ".join(lines))[:limit]


def read_text_preview(path: Path, *, byte_limit: int = 32_000) -> tuple[str, str]:
    if path.suffix.lower() not in TEXT_EXTENSIONS:
        return path.stem.replace("_", " ").replace("-", " "), ""
    raw = path.read_bytes()[:byte_limit]
    text = raw.decode("utf-8", errors="ignore")
    return title_from_text(path, text), useful_snippet(text)

