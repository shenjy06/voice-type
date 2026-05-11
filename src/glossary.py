"""Glossary-based transcript correction."""

from src.config import GlossaryEntry


def apply_glossary(text: str, entries: list[GlossaryEntry]) -> str:
    """Apply user-defined term replacements to recognized text."""
    if not text or not entries:
        return text

    corrected = text
    valid_entries = [
        entry for entry in entries
        if entry.source.strip() and entry.replacement.strip()
    ]
    for entry in sorted(valid_entries, key=lambda item: len(item.source), reverse=True):
        corrected = corrected.replace(entry.source.strip(), entry.replacement.strip())
    return corrected
