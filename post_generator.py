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

CRITICAL RULE : Entire post MUST be in French. Non-negotiable. Only source titles/URLs may be English.

WHAT NEOLEGAL DOES (tell the real story):
- A web platform (B2C) where consumers get legal products : fixed-fee, no hourly rates. Top products: civil, penal, family, business law.
- A lawyer collaboration network : lawyers receive qualified leads without prospecting, generate documents via NeoDoc, and we handle all admin.
- Suite Neolegal Affaire: NeoForm (info collection), NeoDoc (automated document generation), NeoDesk (practice management).
- Avocat dans la Poche: legal access as an employee benefit for insurers and large employers.
- Mission: increase access to justice by unbundling legal products.

Focus areas: legaltech marketing, access to justice, legal product innovation, how tech unbundles legal services, lawyer-client relationships in a digital world.

Rules:
- You are a MARKETER, not a CTO, not a privacy officer. Stay in your lane.
- Bring a FRESH TAKE : say something that adds to the conversation, not rehash what everyone else says.
- HOOK HARD IN THE FIRST LINE. Open with a personal story, a conversation you had, or a sharp observation. NEVER open with "Chez Neolegal".
- "Chez Neolegal" or "notre expérience" max 2 times total, used naturally mid-post as context.
- Neolegal IS an AI/tech platform (NeoDoc, web platform, automated workflows). Never imply Neolegal doesn't do AI or tech.
- Use "produits juridiques" : never "services juridiques".
- USE REAL NUMBERS only when a fresh authorized source is available. Do not force a statistic.
- Reference 0-1 fresh source using EXACT URLs provided. If no fresh source is available, write without any URL.
- INTEGRATE URLs INLINE in the text, right next to the stat they support. NO "Sources:" section at the end.
- Chaque chiffre/statistique doit être immédiatement suivi de sa source URL entre parenthèses. Si aucune URL fraîche n'est autorisée aujourd'hui, n'écris aucun chiffre/statistique externe.
- NEVER invent statistics. Only use numbers you've seen in the provided sources.
- End with a sharp question inviting comment.
- NEVER use bold (**text**).
- NEVER use: "révolution de l'IA", "changer la donne", "à l'ère du digital", "le futur est maintenant", "game changer", "monde numérique", "nouvelle ère", "transformation sans précédent".
- NEVER create false opposition: ne dis pas "alors que les autres / pendant que d'autres / contrairement aux autres" pour sous-entendre que Neolegal ne fait pas d'IA ou de tech.
- FRENCH QUALITY: "pensez-vous" (jamais "penser-vous"), "croyez-vous" (jamais "croire-vous"), conjugue toujours correctement.
- NO EM DASHES: utilise ":" ou "-" au lieu de "—". Jamais de tiret cadratin.
- VARY YOUR SENTENCE STRUCTURE. Don't start three paragraphs in a row with the same word.
- Write 6-8 short paragraphs with line breaks.
"""


SOURCE_REFERENCES = [
    (
        "Neolegal : produits juridiques en ligne, accès à la justice",
        "https://www.neolegal.ca",
    ),
    (
        "LawDroid Legal Aid Plugin : plugin open-source gratuit pour l'aide juridique. 92% des Américains à faible revenu sans aide juridique suffisante (LSC Justice Gap). (mai 2026)",
        "https://www.lawnext.com/2026/05/lawdroid-launches-free-open-source-claude-ai-plugin-for-civil-legal-aid.html",
    ),
    (
        "Fixed-Fee Justice: Angrove Law passe au forfait avec l'IA : prix fixes de 2000-3000$ vs 5000$+ au taux horaire. (avr. 2026)",
        "https://borealsignal.ca/stories/fixed-fee-justice-how-ai-is-reshaping-legal-billing-and-access-to-counsel",
    ),
    (
        "Litera State of Legal AI 2026 : 85% des cabinets subissent la pression client sur l'IA, 51% des clients ont influencé un investissement IA. Seulement 15% des décisions IA sont encore internes.",
        "https://digitalitnews.com/litera-releases-state-of-legal-ai-2026-report/",
    ),
    (
        "Legal Technology Global Market Report 2026 : marché de $36.01B en 2026, croissance 9.2% CAGR, prévu à $51.21B en 2030.",
        "https://www.giiresearch.com/report/tbrc1975880-legal-technology-global-market-report.html",
    ),
    (
        "Thomson Reuters + Anthropic : expansion du partenariat Claude & CoCounsel Legal (mai 2026)",
        "https://www.thomsonreuters.com/en/press-releases/2026/may/thomson-reuters-and-anthropic-expand-partnership-to-connect-claude-with-cocounsel-legal",
    ),
    (
        "2026 Report on the State of the US Legal Market : Thomson Reuters + Georgetown Law. L'industrie juridique américaine: $411B, 165,000+ établissements, 1.09M employés.",
        "https://www.thomsonreuters.com/en/press-releases/2026/january/legal-industry-experiencing-tectonic-shift-technology-talent-and-demand-prompting-law-firms-to-evolve",
    ),
]

SOURCE_URLS = {url for _, url in SOURCE_REFERENCES}
SOURCE_URLS_LIST = list(SOURCE_URLS)
CONTENT_SOURCE_URLS = SOURCE_URLS - {"https://www.neolegal.ca"}
RECENT_HISTORY_LIMIT = 5
ALL_HISTORY_LIMIT = 200

# Known real stats from SOURCE_REFERENCES (used to catch invented numbers)
KNOWN_PERCENTAGES = {"92%", "9.2%", "9,2%", "85%", "51%", "15%"}
KNOWN_DOLLAR_PATTERNS = [r"\$36\.01B", r"\$51\.21B", r"\$411B", r"\$2[\.,]?000", r"\$3[\.,]?000", r"\$5[\.,]?000", r"15\s?000\$"]
KNOWN_COUNTS = {"1.09M", "165 000", "165,000", "5000", "3000", "2000"}

ANGLES = [
    "Un cabinet m'a confié qu'il dépense une part énorme de son budget en prospection vs presque rien sur NeoDoc. Raconte cette conversation.",
    "Un client qui a acheté un forfait droit familial a économisé vs son avocat au taux horaire. Raconte son histoire.",
    "J'ai discuté avec un assureur qui cherche à intégrer Avocat dans la Poche pour ses employés. Explique pourquoi c'est une tendance lourde.",
    "Un avocat collaborateur Neolegal m'a dit qu'il a doublé son chiffre sans toucher à son taux horaire. Comment? NeoDoc et les mandats qualifiés.",
    "Un consommateur m'a écrit hier: 'j'ai eu ma réponse en 10 minutes sur Neolegal, mon avocat mettait 3 jours à me répondre.' Creuse cette différence.",
    "Les cycles de vente legaltech B2C durent quelques jours. B2B dure des mois. Explique ce contraste et pourquoi Neolegal fait les deux.",
    "Un avocat de 60 ans m'a dit: 'je pensais que la tech c'était pour les jeunes, puis j'ai utilisé NeoDoc'. Raconte ce moment de bascule.",
    "92% des gens à faible revenu n'ont pas accès à l'aide juridique suffisante (LSC Justice Gap). Comment les produits à forfait changent ça.",
    "Avant, les cabinets dépensaient des fortunes en Google Ads pour des leads moyens. Avec Neolegal, ça coûte rien pour des mandats qualifiés.",
    "Le taux horaire cache un problème: le client paie pour l'inefficacité du cabinet. Les produits juridiques à forfait alignent les intérêts. Explique.",
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
- OUVRE PAR UNE ACCROCHE PERSONNELLE. Une conversation, une anecdote, une observation du terrain. JAMAIS "Chez Neolegal" en ouverture.
- "Chez Neolegal" ou "notre expérience" max 2 fois dans le post, utilisé naturellement en milieu de texte.
- VARIE TES PHRASES. Ne commence pas deux paragraphes consécutifs par le même mot.
- "produits juridiques" toujours : JAMAIS "services juridiques".
- Neolegal utilise l'IA et la tech (NeoDoc, plateforme, automatisation). Ne sous-entends JAMAIS que Neolegal ne fait pas d'IA.
- Observation concrète du terrain, pas de prédiction vague.
- Utilise un CHIFFRE RÉEL seulement si une source fraîche autorisée est disponible. Sinon, aucun chiffre externe.

RÈGLES STRICTES:
- POST EN FRANÇAIS INTÉGRALEMENT.
- 1800-2500 caractères.
- 6-8 paragraphes courts.
- Ton direct: "cette semaine, un avocat m'a dit...".
- Opinion nette et défendable. Pas de neutralité.
- Pas de hashtags du tout.
- Pas de gras (**).
- N'invente JAMAIS un nom de source ou de rapport. Utilise UNIQUEMENT les URLs autorisées aujourd'hui.
- N'invente JAMAIS de chiffres. Chaque nombre que tu écris doit venir textuellement de la source.
- Chaque chiffre/statistique doit être IMMÉDIATEMENT suivi de sa source URL entre parenthèses. Si aucune URL fraîche n'est autorisée aujourd'hui, n'écris aucun chiffre/statistique externe.
- N'AJOUTE PAS de section "Sources:" à la fin. Les URLs sont intégrées en ligne dans le texte.
- "services juridiques" est INTERDIT. C'est toujours "produits juridiques".
- Ne fais JAMAIS de fausse opposition: ne dis pas "alors que les autres / pendant que d'autres / contrairement aux autres" pour sous-entendre que Neolegal ne fait pas d'IA.
- SOURCES AUTORISÉES AUJOURD'HUI:
{source_rules}
- Termine par une question forte.

MÉMOIRE DES POSTS RÉCENTS:
{history_guidance}

RÈGLES ANTI-RÉPÉTITION:
- Ne répète pas les statistiques, URLs, exemples, hooks ou angles déjà utilisés dans les posts récents.
- Si une statistique comme 85% a déjà servi récemment, elle est interdite aujourd'hui.
- Choisis une seule idée forte. Pas de liste de tendances, pas de collage de rapports, pas de paragraphe "marché global".
- Maximum 1 statistique externe dans tout le post.
- Pas de citation en notes "(1)", "(2)", "(3)". L'URL exacte doit être écrite dans la phrase.
- Pas de section "Source:" à la fin.
- Ne mentionne jamais un prix Neolegal précis sauf s'il est fourni dans les sources autorisées.

PHRASES INTERDITES:
"révolution de l'IA", "changer la donne", "à l'ère du digital", "le futur est maintenant",
"game changer", "monde numérique", "nouvelle ère", "transformation sans précédent",
"services juridiques" (toujours "produits juridiques"), "penser-vous" (toujours "pensez-vous").
"alors que les autres", "pendant que d'autres", "contrairement aux autres" (fausse opposition IA).

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


class TopicTracker:
    """Persists used URLs/angles so we never repeat a topic."""

    def __init__(self, path: str | Path, logger: logging.Logger | None = None) -> None:
        self.path = Path(path)
        self.logger = logger or logging.getLogger(__name__)
        self._used_urls: set[str] = set()
        self._used_angle_indices: set[int] = set()
        self._load()
        self._load_existing_posts()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            raw_urls = set(data.get("used_urls", []))
            self._used_urls = raw_urls & CONTENT_SOURCE_URLS
            self._used_angle_indices = set(data.get("used_angle_indices", []))
            if self._used_urls != raw_urls:
                self.save()
        except (json.JSONDecodeError, KeyError):
            self.logger.warning("Failed to load used_topics.json, starting fresh")

    def _load_existing_posts(self) -> None:
        posts_dir = self.path.parent
        if not posts_dir.exists():
            return

        before = set(self._used_urls)
        for path in posts_dir.glob("*.md"):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            found_urls = {url.rstrip(").,;:!?") for url in re.findall(r"https?://\S+", text)}
            self._used_urls.update(found_urls & CONTENT_SOURCE_URLS)
        if self._used_urls != before:
            self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "used_urls": sorted(self._used_urls),
            "used_angle_indices": sorted(self._used_angle_indices),
        }
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def record(self, post: str) -> None:
        found_urls = {url.rstrip(").,;:!?") for url in re.findall(r"https?://\S+", post)}
        for url in found_urls:
            if url in CONTENT_SOURCE_URLS:
                self._used_urls.add(url)
        self.save()

    def is_url_used(self, url: str) -> bool:
        return url in self._used_urls

    def available_sources(self) -> list[tuple[str, str]]:
        return [(t, u) for t, u in SOURCE_REFERENCES if u not in self._used_urls and u in CONTENT_SOURCE_URLS]

    def available_urls(self) -> list[str]:
        return [u for u in SOURCE_URLS_LIST if u not in self._used_urls]

    def used_urls(self) -> set[str]:
        return set(self._used_urls)

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

        for attempt in range(1, self.config.max_retries + 5):
            try:
                prompt = USER_PROMPT_TEMPLATE.format(
                    today=post_date.isoformat(),
                    angle_instruction=angle,
                    source_rules=self._source_rules(),
                    history_guidance=self._history_guidance(),
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

                cleaned = self._auto_fix(cleaned)
                self._validate_post(cleaned)

                self.topic_tracker.record(cleaned)
                self.logger.info(
                    "POST GENERATED : URL: %s",
                    ", ".join(sorted(set(re.findall(r"https?://\S+", cleaned)) & SOURCE_URLS)) or "neolegal.ca",
                )
                return cleaned

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

Règles:
- "produits juridiques" : pas "services juridiques".
- Pas de hashtags.
- Pas de gras (**).
- Pas de statistiques inventées (X%, "selon une étude").
- Sortie finale entre 1800 et 2500 caractères.
- Ton personnel et direct.
- Garde uniquement une URL déjà présente dans le brouillon. Si le brouillon n'a pas d'URL, n'en ajoute pas.
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
Garde le ton personnel et direct.
Pas de hashtags. Pas de statistiques inventées (X%). "produits juridiques" : pas "services juridiques".
Retourne uniquement le texte raccourci.

Post à raccourcir:
{draft}
"""
        return self._clean_response(self._call_ollama(prompt))

    def _source_rules(self) -> str:
        available_sources = self.topic_tracker.available_sources()
        if not available_sources:
            return (
                "- Aucune source externe fraîche n'est disponible aujourd'hui.\n"
                "- Écris le post sans URL externe et sans statistique externe.\n"
                "- Tu peux mentionner Neolegal comme contexte, mais n'ajoute pas https://www.neolegal.ca juste pour remplir."
            )

        lines = [
            "- Utilise au maximum UNE de ces sources fraîches. N'utilise aucune URL absente de cette liste.",
        ]
        for index, (title, url) in enumerate(available_sources, start=1):
            lines.append(f"  {index}. {title} | {url}")
        lines.append("- Si aucune de ces sources ne sert vraiment l'angle, écris sans URL.")
        return "\n".join(lines)

    @staticmethod
    def _auto_fix(post: str) -> str:
        post = re.sub(r"services?\s+juridiques", "produits juridiques", post, flags=re.IGNORECASE)
        post = re.sub(r"\bpenser-vous\b", "pensez-vous", post, flags=re.IGNORECASE)
        post = re.sub(r"\bcroire-vous\b", "croyez-vous", post, flags=re.IGNORECASE)
        post = post.replace("\u2014", ":").replace("\u2013", "-")
        # normalize "75 %" -> "75%"
        post = re.sub(r"(\d)\s%", r"\1%", post)
        emoji_pattern = re.compile(
            "[\U0001F600-\U0001F64F"
            "\U0001F300-\U0001F5FF"
            "\U0001F680-\U0001F6FF"
            "\U0001F1E0-\U0001F1FF"
            "\U00002702-\U000027B0"
            "\U000024C2-\U0001F251"
            "\U0001F900-\U0001F9FF"
            "\U0001FA00-\U0001FA6F"
            "\U0001FA70-\U0001FAFF"
            "\U00002600-\U000026FF"
            "\U0000FE00-\U0000FE0F]+",
            flags=re.UNICODE,
        )
        post = emoji_pattern.sub("", post)
        return post

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

        banned = [
            "révolution de l'IA", "changer la donne", "à l'ère du digital",
            "le futur est maintenant", "game changer", "monde numérique",
            "nouvelle ère", "transformation sans précédent",
            "alors que les autres", "pendant que d'autres",
            "contrairement aux autres", "c'est une semaine dernière",
            "partagez vos idées avec nous", "marché des produits juridiques est en train de se réveiller",
        ]
        for phrase in banned:
            if phrase.lower() in post.lower():
                raise PostGenerationError(f"Phrase interdite détectée: '{phrase}'")

        match_neolegal = re.findall(r"\bChez Neolegal\b", post)
        if len(match_neolegal) > 3:
            raise PostGenerationError(
                f"'Chez Neolegal' répété {len(match_neolegal)} fois. Maximum 3."
            )

        competitor_names = ["canlii", "clio", "lexisnexis", "practical law", "westlaw"]
        for comp in competitor_names:
            if comp in post.lower():
                raise PostGenerationError(f"Concurrent mentionné: '{comp}'. Interdit.")

        if re.search(r"\*\*.*?\*\*", post):
            raise PostGenerationError("Le post contient du gras (**texte**). Interdit.")

        if re.search(r"\n\s*source\s*:", post, flags=re.IGNORECASE):
            raise PostGenerationError("Section 'Source:' détectée. Les URLs doivent être intégrées en ligne.")

        if re.search(r"\(\s*\d+\s*\)", post):
            raise PostGenerationError("Citation en note détectée: utilise l'URL exacte en ligne, pas (1), (2), etc.")

        found_urls = {url.rstrip(").,;:!?") for url in re.findall(r"https?://\S+", post)}
        invalid_urls = found_urls - SOURCE_URLS
        if invalid_urls:
            raise PostGenerationError(
                f"URL non autorisée détectée: {', '.join(sorted(invalid_urls))}."
            )

        all_urls = self._all_source_urls()
        repeated_urls = (found_urls & CONTENT_SOURCE_URLS) & all_urls
        if repeated_urls:
            raise PostGenerationError(
                f"Source déjà utilisée dans l'historique: {', '.join(sorted(repeated_urls))}."
            )

        # catch invented percentages not in KNOWN_PERCENTAGES
        found_pcts = set(re.findall(r"\b\d+(?:[.,]\d+)?%", post))
        invented_pcts = found_pcts - KNOWN_PERCENTAGES
        if invented_pcts:
            raise PostGenerationError(
                f"Statistique inventée détectée: {', '.join(sorted(invented_pcts))}. "
                f"Seuls les chiffres réels des sources sont autorisés."
            )

        repeated_stats = found_pcts & self._all_percentages()
        if repeated_stats:
            raise PostGenerationError(
                f"Statistique déjà utilisée dans l'historique: {', '.join(sorted(repeated_stats))}."
            )

        if len(found_pcts) > 1:
            raise PostGenerationError("Trop de statistiques dans le post. Maximum 1 statistique externe.")

        if found_pcts and not (found_urls & CONTENT_SOURCE_URLS):
            raise PostGenerationError("Statistique sans source externe fraîche détectée.")

        dollar_values = set(re.findall(
            r"(?:\$|CA\$)\s?\d+(?:[.,]\d+)?\s?(?:B|M|milliards?|millions?)?"
            r"|\d[\d\s]*\s?\$"
            r"|\b\d+(?:[.,]\d+)?\s?(?:milliards?|millions?)\s+de\s+dollars",
            post,
            flags=re.IGNORECASE,
        ))
        allowed_dollar = {
            "$36.01B", "$51.21B", "$411B", "$2,000", "$3,000", "$5,000",
            "$2000", "$3000", "$5000", "15 000$",
        }
        invented_dollars = {value for value in dollar_values if normalize_money(value) not in {normalize_money(item) for item in allowed_dollar}}
        if invented_dollars:
            raise PostGenerationError(
                f"Montant non sourcé détecté: {', '.join(sorted(invented_dollars))}."
            )

        # catch invented fractions like "1/3", "1/2", "2/3" (but not dates "2026/05")
        found_fractions = set(re.findall(r"\b\d+/\d+\b", post))
        real_fractions = {f for f in found_fractions if not re.match(r"\d{4}/\d{1,2}$", f)}
        if real_fractions:
            raise PostGenerationError(
                f"Fraction inventée détectée: {', '.join(sorted(real_fractions))}. "
                f"Pas de fractions non sourcées."
            )

    def _history_guidance(self) -> str:
        recent_posts = self._recent_post_texts()
        if not recent_posts:
            return "- Aucun post récent sauvegardé."

        all_urls = sorted(self._all_source_urls())
        all_pcts = sorted(self._all_percentages())
        hooks = []
        for post in recent_posts:
            first_line = next((line.strip() for line in post.splitlines() if line.strip()), "")
            if first_line:
                hooks.append(first_line[:180])

        lines = [
            "- Interdit de reprendre ces hooks récents: " + " | ".join(hooks[:RECENT_HISTORY_LIMIT]),
        ]
        if all_pcts:
            lines.append("- Statistiques déjà utilisées dans tout l'historique, donc interdites aujourd'hui: " + ", ".join(all_pcts))
        if all_urls:
            lines.append("- URLs déjà utilisées dans tout l'historique, donc interdites aujourd'hui: " + ", ".join(all_urls))
        lines.append("- Ne répète pas les thèmes déjà vus: pression client IA, marché global legaltech, 92% access to justice, taux horaire vs forfait.")
        return "\n".join(lines)

    def _recent_post_texts(self, limit: int = RECENT_HISTORY_LIMIT) -> list[str]:
        candidates = sorted(self.posts_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        posts = []
        for path in candidates[:limit]:
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            posts.append(re.sub(r"^#.*?\n+", "", text, flags=re.DOTALL).strip())
        return posts

    def _recent_source_urls(self) -> set[str]:
        urls: set[str] = set()
        for post in self._recent_post_texts():
            urls.update(url.rstrip(").,;:!?") for url in re.findall(r"https?://\S+", post))
        return urls & CONTENT_SOURCE_URLS

    def _recent_percentages(self) -> set[str]:
        percentages: set[str] = set()
        for post in self._recent_post_texts():
            percentages.update(re.findall(r"\b\d+(?:[.,]\d+)?%", post))
        return percentages

    def _all_post_texts(self, limit: int = ALL_HISTORY_LIMIT) -> list[str]:
        candidates = sorted(self.posts_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        posts = []
        for path in candidates[:limit]:
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            posts.append(re.sub(r"^#.*?\n+", "", text, flags=re.DOTALL).strip())
        return posts

    def _all_source_urls(self) -> set[str]:
        urls: set[str] = self.topic_tracker.used_urls()
        for post in self._all_post_texts():
            urls.update(url.rstrip(").,;:!?") for url in re.findall(r"https?://\S+", post))
        return urls & CONTENT_SOURCE_URLS

    def _all_percentages(self) -> set[str]:
        percentages: set[str] = set()
        for post in self._all_post_texts():
            percentages.update(re.findall(r"\b\d+(?:[.,]\d+)?%", post))
        return percentages


def normalize_money(value: str) -> str:
    return re.sub(r"[\s,.]", "", value).lower().replace("ca$", "$")
