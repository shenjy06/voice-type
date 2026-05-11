"""Tests for voice_type.glossary."""

from src.config import GlossaryEntry
from src.glossary import apply_glossary


def test_apply_glossary_replaces_terms():
    entries = [GlossaryEntry(source="派森", replacement="Python")]

    assert apply_glossary("我想学习派森", entries) == "我想学习Python"


def test_apply_glossary_ignores_empty_entries():
    entries = [
        GlossaryEntry(source="", replacement="Python"),
        GlossaryEntry(source="派森", replacement=""),
        GlossaryEntry(source="扣的", replacement="Codex"),
    ]

    assert apply_glossary("打开扣的", entries) == "打开Codex"


def test_apply_glossary_longer_terms_first():
    entries = [
        GlossaryEntry(source="派森", replacement="Python"),
        GlossaryEntry(source="派森脚本", replacement="Python script"),
    ]

    assert apply_glossary("运行派森脚本", entries) == "运行Python script"


def test_apply_glossary_returns_original_without_entries():
    assert apply_glossary("hello", []) == "hello"
