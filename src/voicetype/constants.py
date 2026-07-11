"""Shared constants used across UI and service modules."""

# Paste mode identifiers — order matters for combo boxes
PASTE_MODE_AUTO = "auto"
PASTE_MODE_CTRL_V = "ctrl_v"
PASTE_MODE_CTRL_SHIFT_V = "ctrl_shift_v"
PASTE_MODE_CLIPBOARD = "clipboard"

# (translation_key, mode_value) pairs for UI listing
PASTE_MODES = (
    ("settings.paste_mode_auto", PASTE_MODE_AUTO),
    ("settings.paste_mode_ctrl_v", PASTE_MODE_CTRL_V),
    ("settings.paste_mode_ctrl_shift_v", PASTE_MODE_CTRL_SHIFT_V),
    ("settings.paste_mode_clipboard", PASTE_MODE_CLIPBOARD),
)

# Available ASR languages (must match what the upstream ASR provider supports)
ASR_LANGUAGES = ("auto", "zh", "en", "ja", "ko", "fr", "de", "es")

# Polish style identifiers
POLISH_STYLE_DEFAULT = "default"
POLISH_STYLE_FORMAL = "formal"
POLISH_STYLE_CASUAL = "casual"
POLISH_STYLE_CONCISE = "concise"

# (translation_key, style_value) pairs for UI listing
POLISH_STYLES = (
    ("settings.polish_style_default", POLISH_STYLE_DEFAULT),
    ("settings.polish_style_formal", POLISH_STYLE_FORMAL),
    ("settings.polish_style_casual", POLISH_STYLE_CASUAL),
    ("settings.polish_style_concise", POLISH_STYLE_CONCISE),
)

# Denoise strength identifiers
DENOISE_STRENGTH_LOW = "low"
DENOISE_STRENGTH_MEDIUM = "medium"
DENOISE_STRENGTH_HIGH = "high"

# (translation_key, strength_value) pairs for UI listing
DENOISE_STRENGTHS = (
    ("settings.denoise_strength_low", DENOISE_STRENGTH_LOW),
    ("settings.denoise_strength_medium", DENOISE_STRENGTH_MEDIUM),
    ("settings.denoise_strength_high", DENOISE_STRENGTH_HIGH),
)

# UI theme modes
THEME_MODE_DARK = "dark"
THEME_MODE_LIGHT = "light"
THEME_MODE_SYSTEM = "system"

# (translation_key, mode_value) pairs for the theme selector
THEME_MODES = (
    ("settings.theme_dark", THEME_MODE_DARK),
    ("settings.theme_light", THEME_MODE_LIGHT),
    ("settings.theme_system", THEME_MODE_SYSTEM),
)
