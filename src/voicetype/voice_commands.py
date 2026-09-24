"""Voice commands — exact-phrase transcripts trigger actions instead of text output.

Matching runs after glossary replacement and before polishing, so ASR
misrecognitions the user has corrected in the glossary still match. The
comparison is normalised (case, whitespace and punctuation stripped) so a
transcript like "换行。" or "New Line!" still hits the "换行" / "new line"
commands.
"""

import logging
import unicodedata

from voicetype.config import VoiceCommandEntry

logger = logging.getLogger(__name__)

# Actions that inject a key sequence into the target window (handled by
# TextTyper.send_action_key). "discard" drops the transcript entirely.
KEY_ACTIONS = ("newline", "enter", "undo", "tab")
DISCARD_ACTION = "discard"
ALL_ACTIONS = KEY_ACTIONS + (DISCARD_ACTION,)


def _normalize(text: str) -> str:
    """Lowercase ``text`` and drop punctuation, symbols and whitespace.

    Matches the desktop implementation (voice-commands.ts, which strips
    ``[\\p{P}\\p{S}\\s]``): characters in categories P*/S*/Z* and all other
    whitespace are removed, while letters, digits and Unicode combining
    marks survive. ``"换行。"`` and ``"New Line!"`` both reduce to the bare
    phrase.
    """
    kept = []
    for ch in text.lower():
        if ch.isspace():
            continue
        if unicodedata.category(ch)[0] in ("P", "S"):
            continue
        kept.append(ch)
    return "".join(kept)


def match_voice_command(
    transcript: str, items: list[VoiceCommandEntry]
) -> str | None:
    """Return the action for ``transcript`` if it exactly matches a command.

    Both sides are normalised before comparison; entries with an empty
    phrase or unknown action are skipped. Returns None when nothing matches.
    """
    target = _normalize(transcript)
    if not target:
        return None
    for item in items:
        phrase = _normalize(item.phrase)
        if phrase and phrase == target and item.action in ALL_ACTIONS:
            logger.info("Voice command matched: %r -> %s", item.phrase, item.action)
            return item.action
    return None
