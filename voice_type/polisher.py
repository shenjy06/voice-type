"""Text polishing via LLM API."""

import logging
from openai import OpenAI
from voice_type.config import AppConfig

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a text refinement assistant. The user speaks naturally, and your job is to:

1. Preserve the original meaning and intent completely — do not add, remove, or change any key points.
2. Remove filler words, repetitions, and self-corrections.
3. Improve grammar, spelling, and sentence structure.
4. Make the expression more natural, clear, and professional.
5. Match the tone and style of the original text — if it's casual, keep it casual; if formal, keep it formal.
6. Detect the input language automatically and refine in the same language.
7. Do NOT add any commentary, explanations, or meta-text. Output ONLY the refined text."""


class TextPolisher:
    def __init__(self, config: AppConfig):
        self.config = config
        self._client = OpenAI(
            api_key=config.polish.api_key,
            base_url=config.polish.base_url,
            timeout=60,
        )

    def polish(self, text: str) -> str:
        """Refine text using the LLM."""
        logger.info("Polishing text: %d chars", len(text))
        response = self._client.chat.completions.create(
            model=self.config.polish.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0.3,
        )
        refined = response.choices[0].message.content.strip()
        logger.info("Polishing complete: %d chars", len(refined))
        return refined
