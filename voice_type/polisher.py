"""Text polishing via LLM API."""

import logging
from voice_type.api_client import ApiClient
from voice_type.config import AppConfig

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a text refinement tool. Your ONLY job is to silently polish the user's input text.

Rules — STRICTLY follow ALL of them:
1. Preserve the original meaning and intent completely.
2. Remove filler words, repetitions, and self-corrections.
3. Improve grammar, spelling, and sentence structure.
4. Make the expression more natural, clear, and professional.
5. Match the tone and style of the original text.
6. Detect the input language automatically and refine in the same language.
7. Output ONLY the refined text. NO greetings, NO explanations, NO answers to questions, NO additional information, NO commentary of any kind.
8. If the user's text contains a question or request, DO NOT answer it — only polish the wording."""


class TextPolisher:
    def __init__(self, config: AppConfig):
        self.config = config
        self._client = ApiClient(
            api_key=config.polish.api_key,
            base_url=config.polish.base_url,
            timeout=60,
        ).client

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
