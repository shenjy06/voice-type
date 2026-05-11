"""Tests for voice_type.i18n."""

import pytest

from src.i18n import init_language, t


@pytest.fixture(autouse=True)
def reset_language():
    init_language("en")
    yield
    init_language("en")


def test_glossary_labels_in_english():
    init_language("en")

    assert t("settings.glossary_tab") == "Glossary"
    assert t("settings.glossary_group") == "Term corrections"
    assert t("settings.glossary_source") == "Recognized text"
    assert t("settings.glossary_replacement") == "Replace with"
    assert t("settings.glossary_add") == "Add Term"
    assert t("settings.glossary_remove") == "Remove Selected"


def test_glossary_labels_in_chinese():
    init_language("zh")

    assert t("settings.glossary_tab") == "词库"
    assert t("settings.glossary_group") == "专有名词修正"
    assert t("settings.glossary_source") == "识别文本"
    assert t("settings.glossary_replacement") == "替换为"
    assert t("settings.glossary_add") == "添加词条"
    assert t("settings.glossary_remove") == "删除选中"
