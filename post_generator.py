"""LinkedIn post generation using a local Ollama model."""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import requests


SYSTEM_PROMPT = """
You are Elizabeth K. Flannery, Director of Marketing at Neolegal (https://www.neolegal.ca), Canada's first digital legal platform. You write LinkedIn posts in your own voice.

CRITICAL RULE — Entire post MUST be in French. Non-negotiable. Only source titles/URLs may be English.

WHAT NEOLEGAL DOES (tell the real story):
- A web platform (B2C) where consumers get legal products — fixed-fee, no hourly rates. Top products: civil, penal, family, business law.
- A lawyer collaboration network — lawyers receive qualified leads without prospecting, generate documents via NeoDoc, and we handle all admin.
- Suite Neolegal Affaire: NeoForm (info collection), NeoDoc (automated document generation), NeoDesk (practice management).
- Avocat dans la Poche: legal access as an employee benefit for insurers and large employers.
- Mission: increase access to justice by unbundling legal products.

Focus areas: legaltech marketing, access to justice, legal product innovation, how tech unbundles legal services, lawyer-client relationships in a digital world.

Rules:
- You are a MARKETER, not a CTO, not a privacy officer. Stay in your lane.
- Bring a FRESH TAKE — say something that adds to the conversation, not rehash what everyone else says.
- Always position Neolegal naturally as the context ("chez Neolegal, on voit que...").
- Use "produits juridiques" — never "services juridiques".
- Hook hard in the first line. No fluff.
- Use 6-9 emojis scattered naturally.
- Reference 1-2 sources using EXACT URLs provided. Do not invent URLs.
- NEVER invent statistics, percentages, or data points. If you write "X% des cabinets" or "selon une étude", you MUST have seen that exact number in the source. If you're not sure, don't include it.
- End with a sharp question inviting comment.
- NEVER use bold (**text**).
- NEVER use: "révolution de l'IA", "changer la donne", "à l'ère du digital", "le futur est maintenant", "game changer", "monde numérique", "nouvelle ère", "transformation sans précédent".
- Write 6-8 short paragraphs with line breaks.
"""


SOURCE_REFERENCES = [
    (
        "Neolegal — produits juridiques en ligne, accès à la justice",
        "https://www.neolegal.ca",
    ),
    (
        "CanLII Search+ — moteur de recherche juridique IA gratuit pour tous les Canadiens (fév. 2026)",
        "https://www.justice-quebec.ca/english-news/3033668_ai-is-moving-into-law-firms-and-canlii-just-opened-the-door-for-everyone",
    ),
    (
        "LawDroid Legal Aid Plugin — plugin open-source gratuit pour l'aide juridique (mai 2026)",
        "https://www.lawnext.com/2026/05/lawdroid-launches-free-open-source-claude-ai-plugin-for-civil-legal-aid.html",
    ),
    (
        "Fixed-Fee Justice: how AI is reshaping legal billing — Angrove Law (avr. 2026)",
        "https://borealsignal.ca/stories/fixed-fee-justice-how-ai-is-reshaping-legal-billing-and-access-to-counsel",
    ),
    (
        "Litera State of Legal AI 2026 — 85% des cabinets subissent la pression client sur l'IA",
        "https://digitalitnews.com/litera-releases-state-of-legal-ai-2026-report/",
    ),
    (
        "Legal Technology Global Market Report 2026 — marché de $36B en 2026, croissance 9.2%",
        "https://www.giiresearch.com/report/tbrc1975880-legal-technology-global-market-report.html",
    ),
    (
        "Thomson Reuters + Anthropic expand Claude & CoCounsel Legal partnership (mai 2026)",
        "https://www.thomsonreuters.com/en/press-releases/2026/may/thomson-reuters-and-anthropic-expand-partnership-to-connect-claude-with-cocounsel-legal",
    ),
    (
        "2026 Report on the State of the US Legal Market — Thomson Reuters + Georgetown Law",
        "https://www.thomsonreuters.com/en/press-releases/2026/january/legal-industry-experiencing-tectonic-shift-technology-talent-and-demand-prompting-law-firms-to-evolve",
    ),
]

SOURCE_URLS = {url for _, url in SOURCE_REFERENCES}
SOURCE_URLS_LIST = list(SOURCE_URLS)

ANGLES = [
    "Point de vue: les cabinets d'avocats qui adoptent le marketing digital gagnent des parts de marché. Donne un exemple concret vu chez Neolegal.",
    "Point de vue: le pricing à forfait vs taux horaire — pourquoi les clients choisissent les produits juridiques décomposés. Observation terrain.",
    "Point de vue: comment les avocats peuvent transformer leur pratique avec des leads qualifiés sans démarchage. Ce que ça change pour leur croissance.",
    "Point de vue: l'accès à la justice passe par la simplicité — ce que j'observe chez les consommateurs de produits juridiques en ligne.",
    "Point de vue: pourquoi les assureurs et grands employeurs ajoutent l'accès juridique aux avantages sociaux. Tendance de fond.",
    "Point de vue: le legal marketing B2C vs B2B — deux mondes, une seule mission : rendre le droit accessible.",
    "Point de vue: ce que la génération de documents automatisée change dans la relation avocat-client.",
    "Point de vue: legaltech et confiance — comment les plateformes comme Neolegal construisent la crédibilité auprès du grand public.",
    "Point de vue: l'essor des produits juridiques à prix fixe — une tendance qui force les cabinets traditionnels à se réinventer.",
    "Point de vue: acquisition client en legaltech — pourquoi le bouche-à-oreille et la simplicité battent les gros budgets pub.",
]


USER_PROMPT_TEMPLATE = """
Écris un post LinkedIn pour Elizabeth K. Flannery, Directrice Marketing chez Neolegal (https://www.neolegal.ca).

Date: {today}
Angle: {angle_instruction}
Audience: dirigeants de cabinets d'avocats, fondateurs legal tech, avocats en pratique privée, équipes marketing B2B legal tech.

CE QUE FAIT NEOLEGAL (sois précise):
- Plateforme web B2C de produits juridiques à forfait (prix fixe, pas de taux horaire). Top produits: droit civil, penal, familial, affaires.
- Réseau d'avocats collaborateurs qui recoivent des mandats qualifiés sans démarchage. NeoDoc genère les documents, Neolegal gère l'admin.
- Suite Neolegal Affaire: NeoForm, NeoDoc, NeoDesk.
- Avocat dans la Poche: avantage employé pour assureurs et grands employeurs.
- Mission: augmenter l'accès à la justice en décomposant les produits juridiques.

TON ET POSITIONNEMENT:
- Directrice marketing, pas une CTO. Jargon technique interdit.
- Apporte UN ANGLE NOUVEAU. Si c'est déjà dit 100 fois, trouve autre chose.
- "produits juridiques" toujours — JAMAIS "services juridiques".
- Mensione Neolegal comme contexte de ton insight: "chez Neolegal, on voit que...", "chez Neolegal, on a constaté...".
- Observation concrète du terrain, pas de prédiction vague.

RÈGLES STRICTES:
- POST EN FRANÇAIS INTÉGRALEMENT.
- 1800-2500 caractères.
- 6-8 paragraphes courts.
- Ton direct: "cette semaine, un avocat m'a dit...".
- Opinion nette et défendable. Pas de neutralité.
- Pas de hashtags du tout.
- Pas de gras (**).
- 6-9 émojis répartis.
- N'invente JAMAIS un nom de source ou de rapport. Utilise UNIQUEMENT les URLs fournies ci-dessous. Ne les modifie pas.
- N'invente JAMAIS de statistiques, pourcentages, ou données chiffrées. Si tu écris "75% des clients" ou "selon une étude", tu DOIS avoir vu ce chiffre exact dans la source. Dans le doute, n'en mets pas.
- "services juridiques" est INTERDIT. C'est toujours "produits juridiques". Si tu écris "services juridiques", le post est rejeté.
- Inclus AU MOINS UNE de ces URLs EXACTES (ce sont les SEULES sources autorisées):
  1. https://www.neolegal.ca
  2. https://www.justice-quebec.ca/english-news/3033668_ai-is-moving-into-law-firms-and-canlii-just-opened-the-door-for-everyone
  3. https://www.lawnext.com/2026/05/lawdroid-launches-free-open-source-claude-ai-plugin-for-civil-legal-aid.html
  4. https://borealsignal.ca/stories/fixed-fee-justice-how-ai-is-reshaping-legal-billing-and-access-to-counsel
  5. https://digitalitnews.com/litera-releases-state-of-legal-ai-2026-report/
  6. https://www.giiresearch.com/report/tbrc1975880-legal-technology-global-market-report.html
  7. https://www.thomsonreuters.com/en/press-releases/2026/may/thomson-reuters-and-anthropic-expand-partnership-to-connect-claude-with-cocounsel-legal
  8. https://www.thomsonreuters.com/en/press-releases/2026/january/legal-industry-experiencing-tectonic-shift-technology-talent-and-demand-prompting-law-firms-to-evolve
- Termine par une question forte.

PHRASES INTERDITES:
"révolution de l'IA", "changer la donne", "à l'ère du digital", "le futur est maintenant",
"game changer", "monde numérique", "nouvelle ère", "transformation sans précédent",
"services juridiques" (toujours "produits juridiques").

Retourne UNIQUEMENT le texte du post LinkedIn. Aucun titre, aucune introduction, aucune explication.
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


class DuplicateTopicError(RuntimeError):
    """Raised when generated post uses an already-used URL."""


class TopicTracker:
    """Persists used URLs/angles so we never repeat a topic."""

    def __init__(self, path: str | Path, logger: logging.Logger | None = None) -> None:
        self.path = Path(path)
        self.logger = logger or logging.getLogger(__name__)
        self._used_urls: set[str] = set()
        self._used_angle_indices: set[int] = set()
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self._used_urls = set(data.get("used_urls", []))
            self._used_angle_indices = set(data.get("used_angle_indices", []))
        except (json.JSONDecodeError, KeyError):
            self.logger.warning("Failed to load used_topics.json, starting fresh")

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "used_urls": sorted(self._used_urls),
            "used_angle_indices": sorted(self._used_angle_indices),
        }
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def record(self, post: str) -> None:
        found_urls = set(re.findall(r"https?://\S+", post))
        for url in found_urls:
            if url in SOURCE_URLS:
                self._used_urls.add(url)
        self.save()

    def is_url_used(self, url: str) -> bool:
        return url in self._used_urls

    def available_sources(self) -> list[tuple[str, str]]:
        return [(t, u) for t, u in SOURCE_REFERENCES if u not in self._used_urls]

    def available_urls(self) -> list[str]:
        return [u for u in SOURCE_URLS_LIST if u not in self._used_urls]

    def fresh_angle(self) -> str:
        unused = [i for i in range(len(ANGLES)) if i not in self._used_angle_indices]
        if not unused:
            self._used_angle_indices.clear()
            unused = list(range(len(ANGLES)))
        idx = unused[0]
        self._used_angle_indices.add(idx)
        self.save()
        return ANGLES[idx]

    def available_angle_count(self) -> int:
        unused = [i for i in range(len(ANGLES)) if i not in self._used_angle_indices]
        return len(unused)

    def total_angles(self) -> int:
        return len(ANGLES)


class PostGenerator:
    """Generates and persists LinkedIn posts."""

    def __init__(
        self,
        ollama_config: OllamaConfig,
        posts_dir: str | Path = "posts",
        logger: logging.Logger | None = None,
        topic_tracker: TopicTracker | None = None,
    ) -> None:
        self.config = ollama_config
        self.posts_dir = Path(posts_dir)
        self.logger = logger or logging.getLogger(__name__)
        self.posts_dir.mkdir(parents=True, exist_ok=True)
        self.topic_tracker = topic_tracker or TopicTracker(self.posts_dir / "used_topics.json", logger)

    def generate_post(self, post_date: date | None = None, angle_instruction: str | None = None) -> str:
        """Generate a LinkedIn post, rotating topics to avoid duplicates."""
        post_date = post_date or date.today()

        angle = angle_instruction or self.topic_tracker.fresh_angle()
        used_count = self.topic_tracker.total_angles() - self.topic_tracker.available_angle_count()
        self.logger.info(
            "=== TOPIC %s/%s: %s",
            used_count + 1,
            self.topic_tracker.total_angles(),
            angle.split(":")[0].replace("Point de vue", "").strip() or angle[:60],
        )

        forbidden_urls = self.topic_tracker.available_urls()
        used_urls = self.topic_tracker._used_urls.copy()

        for attempt in range(1, self.config.max_retries + 5):
            try:
                prompt = USER_PROMPT_TEMPLATE.format(
                    today=post_date.isoformat(),
                    angle_instruction=angle,
                )
                self.logger.info("Generating LinkedIn post with Ollama model %s", self.config.model)
                post = self._call_ollama(prompt)
                cleaned = self._clean_response(post)

                expansion_count = 0
                while len(cleaned) < 1000 and expansion_count < 2:
                    self.logger.info("Post trop court (%s caractères). Expansion en cours.", len(cleaned))
                    cleaned = self._expand_post(cleaned, post_date)
                    expansion_count += 1

                shrink_count = 0
                while len(cleaned) > 2500 and shrink_count < 2:
                    self.logger.info("Post trop long (%s caractères). Raccourcissement en cours.", len(cleaned))
                    cleaned = self._shrink_post(cleaned, post_date)
                    shrink_count += 1

                cleaned = self._ensure_source_url(cleaned)
                self._validate_post(cleaned)

                urls_in_post = set(re.findall(r"https?://\S+", cleaned))
                used_source_urls = urls_in_post & SOURCE_URLS
                repeated = used_source_urls & used_urls

                if repeated:
                    self.logger.warning(
                        "⚠️  DUPLICATE URL DETECTED: %s. Rotating to new topic...",
                        repeated,
                    )
                    angle = self.topic_tracker.fresh_angle()
                    used_urls = self.topic_tracker._used_urls.copy()
                    continue

                self.topic_tracker.record(cleaned)
                self.logger.info(
                    "✅ POST GENERATED — URL: %s",
                    ", ".join(sorted(used_source_urls)) if used_source_urls else "neolegal.ca",
                )
                return cleaned

            except DuplicateTopicError:
                angle = self.topic_tracker.fresh_angle()
                used_urls = self.topic_tracker._used_urls.copy()
                self.logger.info("🔄 Switching to new angle: %s", angle[:80])
                continue

            except Exception as exc:
                self.logger.warning(
                    "Post generation attempt %s/%s failed: %s",
                    attempt,
                    self.config.max_retries + 5,
                    exc,
                )
                if attempt < self.config.max_retries + 5:
                    time.sleep(self.config.retry_delay_seconds)
                    angle = self.topic_tracker.fresh_angle()
                    used_urls = self.topic_tracker._used_urls.copy()

        raise PostGenerationError("Failed to generate a fresh post after exhausting all retries and topics")

    def generate_post_choices(self, post_date: date | None = None, count: int = 3) -> list[str]:
        """Generate several distinct post options for a single date."""
        post_date = post_date or date.today()
        return [self.generate_post(post_date, self.topic_tracker.fresh_angle()) for _ in range(count)]

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
        self.logger.info("💾 Saved LinkedIn post to %s", path)
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
            thinking = data.get("message", {}).get("thinking", "")
            if thinking:
                self.logger.info("Content was empty, extracting answer from thinking field")
                return self._extract_answer_from_thinking(str(thinking))
            raise PostGenerationError(f"Ollama returned an unexpected response: {data}")
        return str(content)

    @staticmethod
    def _extract_answer_from_thinking(thinking: str) -> str:
        candidates = []
        lines = thinking.split("\n")
        half = len(lines) // 2
        candidates.append("\n".join(lines[half:]))
        paragraphs = thinking.split("\n\n")
        if len(paragraphs) > 2:
            candidates.append("\n\n".join(paragraphs[1:]))
        if len(paragraphs) > 4:
            candidates.append("\n\n".join(paragraphs[len(paragraphs) // 2:]))
        last_third_start = len(thinking) * 2 // 3
        candidates.append(thinking[last_third_start:])
        candidates.sort(key=len)
        return candidates[0]

    def _expand_post(self, draft: str, post_date: date) -> str:
        prompt = f"""
Développe ce post LinkedIn en français pour Elizabeth K. Flannery, Directrice Marketing chez Neolegal, afin d'obtenir un post final complet de 1800-2500 caractères.

Date: {post_date.isoformat()}

Conserve l'idée, le hook, les sources, le CTA, mais ajoute:
- une observation marketing plus nette,
- un exemple concret tiré du terrain,
- Neolegal comme contexte naturel ("chez Neolegal..."),
- plus de rythme et de sauts de ligne,
- 6-9 emojis au total.

Règles:
- "produits juridiques" — pas "services juridiques".
- Pas de hashtags.
- Pas de gras (**).
- Pas de statistiques inventées (X%, "selon une étude").
- Sortie finale entre 1800 et 2500 caractères.
- Ton personnel et direct.
- Inclus au moins une URL exacte (parmi la liste autorisée):
  - https://www.neolegal.ca
  - https://www.justice-quebec.ca/english-news/3033668_ai-is-moving-into-law-firms-and-canlii-just-opened-the-door-for-everyone
  - https://www.lawnext.com/2026/05/lawdroid-launches-free-open-source-claude-ai-plugin-for-civil-legal-aid.html
  - https://borealsignal.ca/stories/fixed-fee-justice-how-ai-is-reshaping-legal-billing-and-access-to-counsel
  - https://digitalitnews.com/litera-releases-state-of-legal-ai-2026-report/
  - https://www.giiresearch.com/report/tbrc1975880-legal-technology-global-market-report.html
  - https://www.thomsonreuters.com/en/press-releases/2026/may/thomson-reuters-and-anthropic-expand-partnership-to-connect-claude-with-cocounsel-legal
  - https://www.thomsonreuters.com/en/press-releases/2026/january/legal-industry-experiencing-tectonic-shift-technology-talent-and-demand-prompting-law-firms-to-evolve
- Retourne uniquement le texte final.

Brouillon:
{draft}
"""
        return self._clean_response(self._call_ollama(prompt))

    def _shrink_post(self, draft: str, post_date: date) -> str:
        prompt = f"""
Raccourcis ce post LinkedIn en français à 1800-2500 caractères maximum.
Conserve le hook, l'idée principale, la source URL, le CTA.
Supprime les répétitions, le filler, les phrases trop longues.
Garde le ton personnel et direct. Garde 6-9 émojis.
Pas de hashtags. Pas de statistiques inventées (X%). "produits juridiques" — pas "services juridiques".
Retourne uniquement le texte raccourci.

Post à raccourcir:
{draft}
"""
        return self._clean_response(self._call_ollama(prompt))

    @staticmethod
    def _ensure_source_url(post: str) -> str:
        real_urls = {url for _, url in SOURCE_REFERENCES}
        found_urls = set(re.findall(r"https?://\S+", post))
        if real_urls & found_urls:
            return post
        source_lines = "\n\nSources:\n"
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
        cleaned = re.sub(r"(?i)^voici le post\s*:?\s*", "", cleaned).strip()
        cleaned = re.sub(r"(?i)^option \d+[:\s]*", "", cleaned).strip()
        cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", cleaned)
        return cleaned.strip()

    @staticmethod
    def _markdown_document(post: str, post_date: date) -> str:
        return f"# Daily LinkedIn Post - {post_date.isoformat()}\n\n{post.strip()}\n"

    def _validate_post(self, post: str) -> None:
        char_count = len(post)
        if char_count < 1000:
            raise PostGenerationError(f"Post trop court ({char_count} caractères). Minimum 1000.")
        if char_count > 2500:
            raise PostGenerationError(f"Post trop long ({char_count} caractères). Maximum 2500.")

        if "http://" not in post and "https://" not in post:
            raise PostGenerationError("Aucune URL source trouvée dans le post.")

        if re.search(r"services?\s+juridiques", post, re.IGNORECASE):
            raise PostGenerationError("'services juridiques' détecté. Utilise 'produits juridiques' à la place.")

        banned = [
            "révolution de l'IA", "changer la donne", "à l'ère du digital",
            "le futur est maintenant", "game changer", "monde numérique",
            "nouvelle ère", "transformation sans précédent",
        ]
        for phrase in banned:
            if phrase.lower() in post.lower():
                raise PostGenerationError(f"Phrase interdite détectée: '{phrase}'")

        if re.search(r"\*\*.*?\*\*", post):
            raise PostGenerationError("Le post contient du gras (**texte**). Interdit.")
