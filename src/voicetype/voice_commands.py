"""Voice commands — exact-phrase transcripts trigger actions instead of text output.

Matching runs after glossary replacement and before polishing, so ASR
misrecognitions the user has corrected in the glossary still match. The
comparison is normalised (case, whitespace and punctuation stripped) so a
transcript like "换行。" or "New Line!" still hits the "换行" / "new line"
commands.
"""

import logging

from voicetype.config import VoiceCommandEntry

logger = logging.getLogger(__name__)

# Actions that inject a key sequence into the target window (handled by
# TextTyper.send_action_key). "discard" drops the transcript entirely.
KEY_ACTIONS = ("newline", "enter", "undo", "tab")
DISCARD_ACTION = "discard"
ALL_ACTIONS = KEY_ACTIONS + (DISCARD_ACTION,)


def _normalize(text: str) -> str:
    """Reduce ``text`` to its alphanumeric core (lowercased).

    Chinese characters count as alphanumeric (category Lo), so this keeps
    CJK phrases intact while dropping spaces, punctuation and symbols.
    """
    return "".join(ch.lower() for ch in text if ch.isalnum())


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
