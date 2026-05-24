"""LinkedIn post generation using a local Ollama model."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import requests


SYSTEM_PROMPT = """
You are an elite LinkedIn content strategist specializing in Legal NeoTech Marketing.
Write highly engaging daily LinkedIn posts in French for Elizabeth K. Flannery, Director of Marketing in Legal Tech.

Focus areas: AI in legal, data privacy (GDPR, CCPA), legal innovation, GenAI for law firms, blockchain in legal, future of legal marketing, thought leadership in legal tech.

Rules:
- Write the LinkedIn post itself entirely in French.
- News/source titles and URLs may remain in English.
- Start with a powerful hook.
- Use a personal, executive, direct voice. Avoid sounding like a generic AI essay.
- Use strategic emojis throughout, around 6-9 total.
- Reference 1-2 credible recent sources using exact URLs provided by the user.
- End with an engaging question and invitation to comment.
- Add relevant hashtags.
- Avoid generic phrases like "révolution de l'IA", "changer la donne", "à l'ère du digital", and "le futur est maintenant".
"""


SOURCE_REFERENCES = [
    (
        "Thomson Reuters and Anthropic expand Claude + CoCounsel Legal partnership",
        "https://www.thomsonreuters.com/en/press-releases/2026/may/thomson-reuters-and-anthropic-expand-partnership-to-connect-claude-with-cocounsel-legal",
    ),
    (
        "2026 Report on the State of the US Legal Market, Thomson Reuters + Georgetown Law",
        "https://www.thomsonreuters.com/en/press-releases/2026/january/legal-industry-experiencing-tectonic-shift-technology-talent-and-demand-prompting-law-firms-to-evolve",
    ),
    (
        "IAPP News: privacy, AI governance and digital responsibility",
        "https://iapp.org/news",
    ),
    (
        "Thomson Reuters Institute: 2026 AI in Professional Services report takeaways for legal teams",
        "https://legal.thomsonreuters.com/blog/highlights-from-the-2026-ai-in-professional-services-report-and-what-it-means-for-legal-teams-tri/",
    ),
]


USER_PROMPT_TEMPLATE = """
Crée une option de post LinkedIn du jour pour Elizabeth K. Flannery.

Date: {today}
Angle pour cette option: {angle_instruction}
Audience: dirigeants de cabinets d'avocats, legal operations, fondateurs legal tech, professionnels privacy/data governance, équipes marketing B2B legal tech.
Niche: Legal NeoTech Marketing, l'intersection entre droit, IA, GenAI, blockchain, data privacy, legal tech et stratégies marketing modernes.

Exigences de sortie:
- Le post LinkedIn doit être entièrement en français.
- Les titres des sources peuvent rester en anglais, mais tout le commentaire doit être en français.
- 1400-1900 caractères.
- Écris 6-8 paragraphes courts avec une mini-section source et un CTA.
- Ton personnel, professionnel, audacieux, moderne, clair.
- Écris comme une dirigeante marketing legal tech qui partage une observation vécue, pas comme un rapport.
- Utilise "je" ou "ce que je vois" quand c'est naturel.
- Ajoute une opinion nette, mais défendable.
- Relie le post à au moins une actualité récente ci-dessous.
- Utilise au moins une URL exacte de cette liste:
  1. Thomson Reuters and Anthropic expand Claude + CoCounsel Legal partnership - https://www.thomsonreuters.com/en/press-releases/2026/may/thomson-reuters-and-anthropic-expand-partnership-to-connect-claude-with-cocounsel-legal
  2. 2026 State of the US Legal Market - https://www.thomsonreuters.com/en/press-releases/2026/january/legal-industry-experiencing-tectonic-shift-technology-talent-and-demand-prompting-law-firms-to-evolve
  3. IAPP News: privacy, AI governance and digital responsibility - https://iapp.org/news
  4. Thomson Reuters Institute: AI in Professional Services 2026 - https://legal.thomsonreuters.com/blog/highlights-from-the-2026-ai-in-professional-services-report-and-what-it-means-for-legal-teams-tri/
- Utilise 6-9 emojis maximum, répartis naturellement dans le post.
- Utilise des sauts de ligne fréquents.
- Termine avec une question forte + invitation à commenter.
- Ajoute 4-6 hashtags pertinents à la fin.
- N'utilise pas de titre en gras.
- Évite les formulations génériques comme "la révolution de l'IA", "game changer", "à l'ère du digital", "le futur est maintenant".
- Retourne uniquement le texte du post LinkedIn. Aucune explication.
"""


@dataclass(frozen=True)
class OllamaConfig:
    base_url: str
    model: str
    timeout_seconds: int = 120
    temperature: float = 0.75
    top_p: float = 0.9
    num_predict: int = 1100
    max_retries: int = 3
    retry_delay_seconds: int = 5


class PostGenerationError(RuntimeError):
    """Raised when a post cannot be generated or validated."""


class PostGenerator:
    """Generates and persists LinkedIn posts."""

    def __init__(
        self,
        ollama_config: OllamaConfig,
        posts_dir: str | Path = "posts",
        logger: logging.Logger | None = None,
    ) -> None:
        self.config = ollama_config
        self.posts_dir = Path(posts_dir)
        self.logger = logger or logging.getLogger(__name__)
        self.posts_dir.mkdir(parents=True, exist_ok=True)

    def generate_post(self, post_date: date | None = None, angle_instruction: str | None = None) -> str:
        """Generate one LinkedIn post and validate basic quality constraints."""
        post_date = post_date or date.today()
        prompt = USER_PROMPT_TEMPLATE.format(
            today=post_date.isoformat(),
            angle_instruction=angle_instruction or "Point de vue personnel et stratégique sur une actualité legal tech récente.",
        )

        last_error: Exception | None = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                self.logger.info("Generating LinkedIn post with Ollama model %s", self.config.model)
                post = self._call_ollama(prompt)
                cleaned = self._clean_response(post)
                expansion_count = 0
                while len(cleaned) < 1300 and expansion_count < 2:
                    self.logger.info("Generated post is short (%s characters). Expanding draft.", len(cleaned))
                    cleaned = self._expand_post(cleaned, post_date)
                    expansion_count += 1
                cleaned = self._ensure_source_url(cleaned)
                self._validate_post(cleaned)
                return cleaned
            except Exception as exc:  # noqa: BLE001 - surfaced with context after retries.
                last_error = exc
                self.logger.warning(
                    "Post generation attempt %s/%s failed: %s",
                    attempt,
                    self.config.max_retries,
                    exc,
                )
                if attempt < self.config.max_retries:
                    time.sleep(self.config.retry_delay_seconds)

        raise PostGenerationError(f"Failed to generate a valid post: {last_error}") from last_error

    def generate_post_choices(self, post_date: date | None = None, count: int = 3) -> list[str]:
        """Generate several distinct post options for a single date."""
        post_date = post_date or date.today()
        angles = [
            "Option 1: prise de position personnelle sur une actualité GenAI/legal tech récente.",
            "Option 2: framework pratique pour transformer une news IA/legal tech en confiance client.",
            "Option 3: angle data privacy/AI governance avec une opinion plus contrarienne.",
        ]
        return [self.generate_post(post_date, angles[index % len(angles)]) for index in range(count)]

    def save_post(
        self,
        post: str,
        post_date: date | None = None,
        overwrite: bool = False,
        suffix: str = "",
    ) -> Path:
        """Save the generated post to ./posts/YYYY-MM-DD-linkedin-post.md."""
        post_date = post_date or date.today()
        path = self.posts_dir / f"{post_date.isoformat()}-linkedin-post{suffix}.md"

        if path.exists() and not overwrite:
            timestamp = int(time.time())
            path = self.posts_dir / f"{post_date.isoformat()}-linkedin-post{suffix}-{timestamp}.md"

        path.write_text(self._markdown_document(post, post_date), encoding="utf-8")
        self.logger.info("Saved LinkedIn post to %s", path)
        return path

    def latest_post_path(self) -> Path | None:
        """Return the newest saved post path, if any."""
        candidates = sorted(self.posts_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        return candidates[0] if candidates else None

    def _call_ollama(self, prompt: str) -> str:
        endpoint = f"{self.config.base_url.rstrip('/')}/api/chat"
        payload: dict[str, Any] = {
            "model": self.config.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT.strip()},
                {"role": "user", "content": prompt.strip()},
            ],
            "options": {
                "temperature": self.config.temperature,
                "top_p": self.config.top_p,
                "num_predict": self.config.num_predict,
            },
        }

        response = requests.post(endpoint, json=payload, timeout=self.config.timeout_seconds)
        response.raise_for_status()
        data = response.json()

        content = data.get("message", {}).get("content")
        if not content:
            raise PostGenerationError(f"Ollama returned an unexpected response: {data}")
        return str(content)

    def _expand_post(self, draft: str, post_date: date) -> str:
        prompt = f"""
Développe ce post LinkedIn en français pour Elizabeth K. Flannery afin d'obtenir un post final complet de 1400-1900 caractères.

Date: {post_date.isoformat()}

Conserve l'idée, le hook, les sources, le CTA et les hashtags, mais ajoute:
- une analyse exécutive plus nette,
- un framework pratique très court,
- une implication plus forte pour le Legal NeoTech Marketing,
- plus de rythme et de sauts de ligne,
- 6-9 emojis au total.

Règles:
- Sortie finale entièrement en français.
- Les titres de sources peuvent rester en anglais.
- Sortie finale entre 1400 et 1900 caractères.
- Utilise 6-9 emojis maximum.
- Ton personnel, direct, moins "IA générative".
- N'utilise pas de titre en gras.
- Inclus au moins une URL exacte:
  - https://www.thomsonreuters.com/en/press-releases/2026/may/thomson-reuters-and-anthropic-expand-partnership-to-connect-claude-with-cocounsel-legal
  - https://www.thomsonreuters.com/en/press-releases/2026/january/legal-industry-experiencing-tectonic-shift-technology-talent-and-demand-prompting-law-firms-to-evolve
  - https://iapp.org/news
  - https://legal.thomsonreuters.com/blog/highlights-from-the-2026-ai-in-professional-services-report-and-what-it-means-for-legal-teams-tri/
- Retourne uniquement le texte final du post LinkedIn.

Brouillon:
{draft}
"""
        return self._clean_response(self._call_ollama(prompt))

    @staticmethod
    def _ensure_source_url(post: str) -> str:
        if "http://" in post or "https://" in post:
            return post

        source_lines = "\n\nSources à lire:\n"
        source_lines += "\n".join(f"- {title}: {url}" for title, url in SOURCE_REFERENCES[:2])
        return f"{post.rstrip()}{source_lines}"

    @staticmethod
    def _clean_response(text: str) -> str:
        cleaned = text.strip()
        cleaned = re.sub(r"^```(?:markdown|text)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = re.sub(r"(?i)^here is the final linkedin post text:\s*", "", cleaned).strip()
        cleaned = re.sub(r"(?i)^here'?s the final linkedin post:\s*", "", cleaned).strip()
        cleaned = re.sub(r"(?i)^here is the linkedin post:\s*", "", cleaned).strip()
        cleaned = re.sub(r"(?i)^voici le post linkedin final\s*:?\s*", "", cleaned).strip()
        return cleaned.strip()

    @staticmethod
    def _markdown_document(post: str, post_date: date) -> str:
        return f"# Daily LinkedIn Post - {post_date.isoformat()}\n\n{post.strip()}\n"

    def _validate_post(self, post: str) -> None:
        char_count = len(post)
        if char_count < 1300:
            raise PostGenerationError(f"Generated post is too short ({char_count} characters).")
        if char_count > 2200:
            raise PostGenerationError(f"Generated post is too long ({char_count} characters).")

        hashtags = re.findall(r"#[^\s#]+", post)
        if len(hashtags) < 4:
            raise PostGenerationError("Generated post does not include enough hashtags.")

        if "http://" not in post and "https://" not in post:
            raise PostGenerationError("Generated post does not include an external source URL.")
