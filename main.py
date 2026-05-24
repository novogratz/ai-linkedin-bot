"""Daily LinkedIn post generator and email scheduler."""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from types import FrameType
from typing import Any

import schedule

from email_sender import EmailConfig, EmailSender
from post_generator import OllamaConfig, PostGenerator


DEFAULT_CONFIG_PATH = Path("config.json")
DEFAULT_ENV_PATH = Path(".env")


@dataclass(frozen=True)
class AppConfig:
    ollama: OllamaConfig
    email: EmailConfig
    daily_time: str
    timezone: str
    posts_dir: Path
    logs_dir: Path


class DailyLinkedInBot:
    """Coordinates generation, persistence, and email delivery."""

    def __init__(self, config: AppConfig, logger: logging.Logger) -> None:
        self.config = config
        self.logger = logger
        self.generator = PostGenerator(config.ollama, config.posts_dir, logger)
        self.email_sender = EmailSender(config.email, logger)
        self._shutdown_requested = False

    def run_once(self, overwrite_today: bool = False) -> Path:
        """Generate, save, and email today's LinkedIn post."""
        today = date.today()
        return self.run_for_date(today, overwrite=overwrite_today)

    def run_for_date(self, post_date: date, overwrite: bool = False) -> Path:
        """Generate, save, and email three LinkedIn post choices for a specific date."""
        self.logger.info("Starting LinkedIn post workflow for %s", post_date.isoformat())
        posts = self.generator.generate_post_choices(post_date, count=3)
        saved_paths = [
            self.generator.save_post(post, post_date, overwrite=overwrite, suffix=f"-option-{index}")
            for index, post in enumerate(posts, start=1)
        ]
        self.email_sender.send_post_choices(posts, post_date)
        self.logger.info("LinkedIn post workflow completed")
        return saved_paths[0]

    def regenerate_last(self) -> Path:
        """Regenerate the most recently saved post, or today's post if none exists."""
        latest_path = self.generator.latest_post_path()
        post_date = parse_date_from_post_path(latest_path) if latest_path else date.today()
        self.logger.info("Regenerating LinkedIn post for %s", post_date.isoformat())
        return self.run_for_date(post_date, overwrite=True)

    def generate_week(self, start_date: date | None = None, days: int = 7) -> list[Path]:
        """Generate and save a post for each day in a week without emailing."""
        start_date = start_date or date.today()
        saved_paths: list[Path] = []

        for offset in range(days):
            post_date = start_date + timedelta(days=offset)
            self.logger.info("Generating weekly draft for %s", post_date.isoformat())
            posts = self.generator.generate_post_choices(post_date, count=3)
            for index, post in enumerate(posts, start=1):
                saved_paths.append(
                    self.generator.save_post(post, post_date, overwrite=True, suffix=f"-option-{index}")
                )

        return saved_paths

    def run_scheduler(self) -> None:
        """Run the process daily until a shutdown signal is received."""
        schedule.every().day.at(self.config.daily_time, self.config.timezone).do(self.run_once)
        self.logger.info(
            "Scheduler started. Daily run time: %s %s",
            self.config.daily_time,
            self.config.timezone,
        )

        while not self._shutdown_requested:
            schedule.run_pending()
            time.sleep(1)

        self.logger.info("Scheduler stopped")

    def request_shutdown(self, signum: int, _frame: FrameType | None) -> None:
        self.logger.info("Received signal %s. Shutting down gracefully.", signum)
        self._shutdown_requested = True


def load_config(path: Path) -> AppConfig:
    """Load and validate config.json."""
    load_env_file(DEFAULT_ENV_PATH)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    raw: dict[str, Any] = expand_env_values(json.loads(path.read_text(encoding="utf-8")))

    ollama_raw = raw.get("ollama", {})
    email_raw = raw.get("email", {})
    schedule_raw = raw.get("schedule", {})
    storage_raw = raw.get("storage", {})

    ollama = OllamaConfig(
        base_url=ollama_raw.get("base_url", "http://localhost:11434"),
        model=ollama_raw.get("model", "llama3.2"),
        timeout_seconds=int(ollama_raw.get("timeout_seconds", 120)),
        temperature=float(ollama_raw.get("temperature", 0.75)),
        top_p=float(ollama_raw.get("top_p", 0.9)),
        num_predict=int(ollama_raw.get("num_predict", 1100)),
        max_retries=int(ollama_raw.get("max_retries", 3)),
        retry_delay_seconds=int(ollama_raw.get("retry_delay_seconds", 5)),
    )

    email = EmailConfig(
        smtp_host=require_config(email_raw, "smtp_host"),
        smtp_port=int(email_raw.get("smtp_port", 587)),
        use_tls=bool(email_raw.get("use_tls", True)),
        username=email_raw.get("username", ""),
        password=email_raw.get("password", ""),
        from_email=require_config(email_raw, "from_email"),
        from_name=email_raw.get("from_name", "KzerAI Daily LinkedIn Bot"),
        to_email=email_raw.get("to_email", "elizabethkflannery@gmail.com"),
        max_retries=int(email_raw.get("max_retries", 3)),
        retry_delay_seconds=int(email_raw.get("retry_delay_seconds", 5)),
    )

    daily_time = schedule_raw.get("daily_time", "06:00")
    if not isinstance(daily_time, str) or not daily_time:
        raise ValueError("schedule.daily_time must be a non-empty HH:MM string")
    timezone = schedule_raw.get("timezone", "America/Toronto")
    if not isinstance(timezone, str) or not timezone:
        raise ValueError("schedule.timezone must be a non-empty timezone string")

    return AppConfig(
        ollama=ollama,
        email=email,
        daily_time=daily_time,
        timezone=timezone,
        posts_dir=Path(storage_raw.get("posts_dir", "posts")),
        logs_dir=Path(storage_raw.get("logs_dir", "logs")),
    )


def require_config(section: dict[str, Any], key: str) -> str:
    value = section.get(key)
    if not value:
        raise ValueError(f"Missing required config value: {key}")
    return str(value)


def load_env_file(path: Path) -> None:
    """Load KEY=value pairs from a local .env file without overriding the process env."""
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def expand_env_values(value: Any) -> Any:
    """Recursively expand ${VAR_NAME} placeholders in loaded JSON config."""
    if isinstance(value, dict):
        return {key: expand_env_values(item) for key, item in value.items()}
    if isinstance(value, list):
        return [expand_env_values(item) for item in value]
    if isinstance(value, str):
        return os.path.expandvars(value)
    return value


def parse_date_from_post_path(path: Path | None) -> date:
    """Extract YYYY-MM-DD from a saved post filename."""
    if path is None:
        return date.today()

    try:
        return date.fromisoformat(path.name[:10])
    except ValueError:
        return date.today()


def setup_logging(logs_dir: Path) -> logging.Logger:
    logs_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("daily_linkedin_bot")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    file_handler = logging.FileHandler(logs_dir / "daily_linkedin_bot.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate and email daily LinkedIn posts.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to config.json")
    parser.add_argument("--today", action="store_true", help="Generate and email today's post now")
    parser.add_argument("--regenerate", action="store_true", help="Regenerate and email the most recent saved post")
    parser.add_argument("--week", action="store_true", help="Generate and save seven days of three options without emailing")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        config = load_config(Path(args.config))
        logger = setup_logging(config.logs_dir)
        bot = DailyLinkedInBot(config, logger)

        signal.signal(signal.SIGINT, bot.request_shutdown)
        signal.signal(signal.SIGTERM, bot.request_shutdown)

        if args.today:
            saved_path = bot.run_once()
            logger.info("Manual run saved post at %s", saved_path)
            return 0

        if args.regenerate:
            saved_path = bot.regenerate_last()
            logger.info("Regenerated post saved at %s", saved_path)
            return 0

        if args.week:
            saved_paths = bot.generate_week()
            logger.info("Generated %s weekly drafts", len(saved_paths))
            for path in saved_paths:
                logger.info("Weekly draft saved at %s", path)
            return 0

        bot.run_scheduler()
        return 0
    except Exception as exc:  # noqa: BLE001 - top-level CLI guard.
        logging.basicConfig(level=logging.ERROR)
        logging.exception("Fatal error: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
