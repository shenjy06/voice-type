"""Scene presets — pick a config profile from the foreground window's process.

When recording starts, the foreground window's executable name (e.g.
"Code.exe") is matched against the configured rules; the first rule whose
``match`` text is a substring of the process name (case-insensitive) wins
and its profile is used as the session config for that recording cycle.
"""

import logging

from voicetype.config import SceneRule

logger = logging.getLogger(__name__)


def match_scene_profile(process_name: str, rules: list[SceneRule]) -> str | None:
    """Return the profile name of the first rule matching ``process_name``.

    Matching is a case-insensitive substring test; rules with an empty
    ``match`` or ``profile`` are skipped. Returns None when nothing matches.
    """
    proc = process_name.lower()
    if not proc:
        return None
    for rule in rules:
        needle = rule.match.strip().lower()
        if needle and rule.profile.strip() and needle in proc:
            logger.info(
                "Scene rule matched: %r in process %r -> profile %r",
                rule.match,
                process_name,
                rule.profile,
            )
            return rule.profile.strip()
    return None
