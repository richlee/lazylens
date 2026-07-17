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

BOILERPLATE_PREFIXES = (
    "author:",
    "created:",
    "created by:",
    "document type",
    "last updated:",
    "linked document",
    "linked documents",
    "owner:",
    "purpose",
    "status",
    "updated:",
)

STANDALONE_BOILERPLATE_LABELS = {
    "author",
    "created",
    "created by",
    "document type",
    "last updated",
    "linked document",
    "linked documents",
    "owner",
    "purpose",
    "status",
    "updated",
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


def useful_snippet(text: str, *, limit: int = 1_200) -> str:
    paragraphs = useful_paragraphs(text)
    if not paragraphs:
        return ""

    selected = []
    for paragraph in paragraphs:
        if not selected and not is_genuine_paragraph(paragraph):
            continue
        if selected and not is_genuine_paragraph(paragraph, minimum_length=60):
            continue
        selected.append(paragraph)
        if len(" ".join(selected)) >= limit:
            break
    if not selected:
        selected = [paragraphs[0]]
    return truncate_text(" ".join(selected), limit)


def useful_paragraphs(text: str) -> list[str]:
    paragraphs = []
    current = []
    in_frontmatter = False
    seen_content = False
    skip_next_value = False

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            append_paragraph(paragraphs, current)
            continue

        if skip_next_value:
            skip_next_value = False
            seen_content = True
            continue

        if stripped in {"---", "+++"} and not seen_content:
            in_frontmatter = True
            seen_content = True
            continue
        if in_frontmatter:
            if stripped in {"---", "+++"}:
                in_frontmatter = False
            continue

        if is_noise_line(stripped):
            append_paragraph(paragraphs, current)
            skip_next_value = is_standalone_boilerplate_label(stripped)
            seen_content = True
            continue
        current.append(stripped)
        seen_content = True
    append_paragraph(paragraphs, current)
    return paragraphs


def append_paragraph(paragraphs: list[str], current: list[str]) -> None:
    if not current:
        return
    paragraph = compact_text(" ".join(current))
    if paragraph:
        paragraphs.append(paragraph)
    current.clear()


def is_noise_line(value: str) -> bool:
    lowered = value.lower().strip()
    return (
        lowered.startswith(("#", "```"))
        or lowered in {"---", "+++"}
        or lowered.startswith(BOILERPLATE_PREFIXES)
        or is_standalone_boilerplate_label(value)
    )


def is_standalone_boilerplate_label(value: str) -> bool:
    return value.lower().strip().rstrip(":") in STANDALONE_BOILERPLATE_LABELS


def is_genuine_paragraph(value: str, *, minimum_length: int = 80) -> bool:
    words = re.findall(r"\w+", value)
    if len(value) < minimum_length or len(words) < 10:
        return False
    if value.count(" | ") >= 2:
        return False
    return True


def truncate_text(value: str, limit: int) -> str:
    compacted = compact_text(value)
    if len(compacted) <= limit:
        return compacted
    truncated = compacted[:limit].rsplit(" ", 1)[0].rstrip(" ,.;:")
    return truncated or compacted[:limit]


def read_text_preview(path: Path, *, byte_limit: int = 32_000) -> tuple[str, str]:
    if path.suffix.lower() not in TEXT_EXTENSIONS:
        return path.stem.replace("_", " ").replace("-", " "), ""
    raw = path.read_bytes()[:byte_limit]
    text = raw.decode("utf-8", errors="ignore")
    return title_from_text(path, text), useful_snippet(text)
