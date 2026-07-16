from __future__ import annotations

from pathlib import Path

from lazylens.extract import read_text_preview, useful_snippet


def test_useful_snippet_skips_markdown_noise() -> None:
    text = """
# Architecture Notes

---

This page explains the useful part.
It has enough context to preview.
"""

    assert useful_snippet(text) == "This page explains the useful part. It has enough context to preview."


def test_read_text_preview_uses_markdown_heading(tmp_path: Path) -> None:
    doc = tmp_path / "platform-notes.md"
    doc.write_text("# Platform Notes\n\nImportant architecture context.")

    title, snippet = read_text_preview(doc)

    assert title == "Platform Notes"
    assert snippet == "Important architecture context."

