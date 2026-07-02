"""Glossary-based transcript correction."""

import re

from voicetype.config import GlossaryEntry

# Cache the compiled regex + replacement map. The key is a tuple of
# (source, replacement) pairs; it changes only when settings are saved.
# The list object identity works because config.glossary is replaced wholesale
# on load/save, but a content-derived key is safer for mutations in place.
_glossary_cache: dict[tuple[tuple[str, str], ...], tuple[re.Pattern, dict[str, str]]] = {}


def _build_glossary_cache(entries: list[GlossaryEntry]) -> tuple[re.Pattern, dict[str, str]] | None:
    """Build (or retrieve from cache) the compiled regex and replacement map."""
    valid = [
        (entry.source.strip(), entry.replacement.strip())
        for entry in entries
        if entry.source.strip() and entry.replacement.strip()
    ]
    if not valid:
        return None

    key = tuple(sorted(valid, key=lambda item: len(item[0]), reverse=True))
    cached = _glossary_cache.get(key)
    if cached is not None:
        return cached

    # Keep only the first occurrence of each source when duplicates exist.
    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for source, replacement in key:
        if source not in seen:
            seen.add(source)
            unique.append((source, replacement))

    pattern = re.compile("|".join(re.escape(source) for source, _ in unique))
    replacement_map = {source: replacement for source, replacement in unique}

    # Bound cache size — evict if it grows too large (unlikely in practice).
    if len(_glossary_cache) > 16:
        _glossary_cache.clear()

    result = (pattern, replacement_map)
    _glossary_cache[key] = result
    return result


def invalidate_glossary_cache() -> None:
    """Drop the compiled glossary cache (call after settings change)."""
    _glossary_cache.clear()


def apply_glossary(text: str, entries: list[GlossaryEntry]) -> str:
    """Apply user-defined term replacements to recognized text."""
    if not text or not entries:
        return text

    cached = _build_glossary_cache(entries)
    if cached is None:
        return text

    pattern, replacement_map = cached
    return pattern.sub(lambda m: replacement_map[m.group(0)], text)
